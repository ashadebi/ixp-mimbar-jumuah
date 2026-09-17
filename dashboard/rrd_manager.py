import contextlib
import fcntl
import math
import os, re, sqlite3, subprocess, sys, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("MIMBAR_DATA", ROOT / "data")).resolve()
RRD_DIR = DATA / "rrd"
DB_PATH = DATA / "mimbar.sqlite3"
SCHEDULER_MODE_PATH = DATA / "rrd-scheduler"
LOCK_PATH = DATA / "rrd-poller.lock"
RRD_COMMAND_TIMEOUT = int(os.environ.get("MIMBAR_RRD_COMMAND_TIMEOUT", "30"))
SNMP_WALK_TIMEOUT = int(os.environ.get("MIMBAR_SNMP_WALK_TIMEOUT", "10"))
SNMP_GET_TIMEOUT = int(os.environ.get("MIMBAR_SNMP_GET_TIMEOUT", "8"))
_collector_thread = None
_collector_lock = threading.Lock()

def init_rrd_dir():
    DATA.mkdir(parents=True, exist_ok=True)
    RRD_DIR.mkdir(parents=True, exist_ok=True)

def get_rrd_path(switch_id, port_id):
    init_rrd_dir()
    return RRD_DIR / f"port_{int(switch_id)}_{int(port_id)}.rrd"

def _run(cmd, timeout, **kwargs):
    return subprocess.run(cmd, timeout=timeout, **kwargs)

def ensure_rrd(switch_id, port_id):
    p = get_rrd_path(switch_id, port_id)
    if not p.exists():
        _run(
            [
                "rrdtool", "create", str(p),
                "--start", str(int(time.time()) - 300),
                "--step", "300",
                "DS:in:COUNTER:600:0:U",
                "DS:out:COUNTER:600:0:U",
                "RRA:AVERAGE:0.5:1:576"
            ],
            timeout=RRD_COMMAND_TIMEOUT,
            check=True
        )
    return p

def update_rrd(switch_id, port_id, bytes_in, bytes_out, timestamp=None):
    ts = 'N' if timestamp is None else int(timestamp)
    _run(
        ["rrdtool", "update", str(ensure_rrd(switch_id, port_id)), f"{ts}:{int(bytes_in)}:{int(bytes_out)}"],
        timeout=RRD_COMMAND_TIMEOUT,
        check=True
    )

def generate_graph_png(switch_id, port_id, start="-48h", title=None):
    p = ensure_rrd(switch_id, port_id)
    t = title if title else f'Utilisasi Port {port_id}'
    args = [
        "rrdtool", "graph", "-",
        "--start", start, "--end", "now",
        "--title", str(t)[:80],
        "--vertical-label", "bits/sec",
        "--width", "600", "--height", "200",
        f"DEF:i={p}:in:AVERAGE",
        f"DEF:o={p}:out:AVERAGE",
        "CDEF:ib=i,8,*",
        "CDEF:ob=o,8,*",
        "CDEF:upload=ob,-1,*",
        "AREA:ib#16A34A:Download",
        "AREA:upload#2563EB:Upload",
        "HRULE:0#64748B"
    ]
    return _run(args, timeout=RRD_COMMAND_TIMEOUT, capture_output=True, check=True).stdout

def fetch_rrd_data(switch_id, port_id, start="-48h"):
    p = ensure_rrd(switch_id, port_id)
    out = _run(["rrdtool", "fetch", str(p), "AVERAGE", "--start", start, "--end", "now"], timeout=RRD_COMMAND_TIMEOUT, capture_output=True, text=True, check=True).stdout
    result = []
    for line in out.splitlines()[2:]:
        m = re.match(r"\s*(\d+):\s+(\S+)\s+(\S+)", line)
        if not m:
            continue
        def val(x):
            try:
                v = float(x)
                return round(v * 8, 2) if math.isfinite(v) else None
            except ValueError:
                return None
        result.append({'timestamp': int(m[1]), 'in_bps': val(m[2]), 'out_bps': val(m[3])})
    return result

def _inventory():
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(DB_PATH, timeout=10) as c:
        c.row_factory = sqlite3.Row
        return [dict(x) for x in c.execute("SELECT s.id switch_id, s.ip, s.community, p.id port_id, p.port_number FROM switches s JOIN ports p ON p.switch_id=s.id")]

def _values(stdout):
    vals = []
    for line in stdout.splitlines():
        m = re.search(r"(?:Counter32|Counter64|INTEGER|Gauge32):\s*(\d+)\s*$", line)
        if m:
            vals.append(int(m[1]))
    return vals

def _safe_log(message):
    print(message, file=sys.stderr)

@contextlib.contextmanager
def _poll_lock(blocking=False):
    init_rrd_dir()
    with LOCK_PATH.open("w") as fh:
        flags = fcntl.LOCK_EX
        if not blocking:
            flags |= fcntl.LOCK_NB
        try:
            fcntl.flock(fh.fileno(), flags)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

def poll_snmp_once():
    with _poll_lock(blocking=False) as acquired:
        if not acquired:
            _safe_log("RRD poll dilewati: poller lain masih berjalan")
            return False
        _poll_snmp_once_unlocked()
        return True

def _poll_snmp_once_unlocked():
    items = _inventory()
    if not items:
        return
    by_switch = {}
    for x in items:
        by_switch.setdefault(x['switch_id'], []).append(x)
    
    for sw_id, ports in by_switch.items():
        sw_ip = ports[0]['ip']
        sw_comm = ports[0]['community']
        ifindex_map = {}
        
        need_walk = any(not str(p['port_number']).isdigit() for p in ports)
        if need_walk:
            try:
                z = _run(["snmpwalk", "-v2c", "-c", sw_comm, "-t", "3", "-r", "1", sw_ip, ".1.3.6.1.2.1.31.1.1.1.1"], timeout=SNMP_WALK_TIMEOUT, capture_output=True, text=True)
                for line in z.stdout.splitlines():
                    m = re.search(r'(?:iso\.3|1)\.6\.1\.2\.1\.31\.1\.1\.1\.1\.(\d+)\s*=\s*(.+)$', line)
                    if m:
                        idx = int(m.group(1))
                        raw = m.group(2).strip().strip('"')
                        if 'STRING:' in raw:
                            raw = raw.split('STRING:', 1)[1].strip().strip('"')
                        ifindex_map[raw] = idx
            except Exception as e:
                _safe_log(f"SNMP walk ifName gagal switch={sw_id}: {type(e).__name__}: {e}")
        
        base = ["snmpget", "-v2c", "-c", sw_comm, "-t", "2", "-r", "1", sw_ip]
        for x in ports:
            pn = str(x['port_number']).strip()
            if pn.isdigit():
                n = int(pn)
            else:
                n = ifindex_map.get(pn)
            if not n:
                continue
            try:
                hc = base + [f"1.3.6.1.2.1.31.1.1.1.6.{n}", f"1.3.6.1.2.1.31.1.1.1.10.{n}"]
                z = _run(hc, timeout=SNMP_GET_TIMEOUT, capture_output=True, text=True)
                vals = _values(z.stdout)
                if z.returncode != 0 or len(vals) != 2:
                    z = _run(base + [f"1.3.6.1.2.1.2.2.1.10.{n}", f"1.3.6.1.2.1.2.2.1.16.{n}"], timeout=SNMP_GET_TIMEOUT, capture_output=True, text=True)
                    vals = _values(z.stdout)
                if z.returncode == 0 and len(vals) == 2:
                    update_rrd(x['switch_id'], x['port_id'], *vals)
            except Exception as e:
                _safe_log(f"RRD poll gagal switch={x['switch_id']} port={x['port_id']}: {type(e).__name__}: {e}")

def _scheduler_mode():
    try:
        return SCHEDULER_MODE_PATH.read_text().strip().lower()
    except FileNotFoundError:
        return "background"
    except Exception as e:
        _safe_log(f"Mode scheduler RRD tidak bisa dibaca: {type(e).__name__}: {e}")
        return "background"

def set_scheduler_mode(mode):
    mode = str(mode).strip().lower()
    if mode not in {"background", "cron"}:
        raise ValueError("mode scheduler RRD tidak valid")
    DATA.mkdir(parents=True, exist_ok=True)
    SCHEDULER_MODE_PATH.write_text(mode + "\n")

def start_background_collector(interval_sec=300):
    global _collector_thread
    if _scheduler_mode() == "cron":
        return False
    with _collector_lock:
        if _collector_thread is not None and _collector_thread.is_alive():
            return False
        def loop():
            while True:
                poll_snmp_once()
                time.sleep(interval_sec)
        _collector_thread = threading.Thread(target=loop, name='rrd-collector', daemon=True)
        _collector_thread.start()
        return True

def generate_aggregate_graph_png(port_refs, start="-48h", title="Agregat Traffic"):
    refs = []
    for switch_id, port_id in port_refs:
        path = get_rrd_path(switch_id, port_id)
        if path.exists():
            refs.append((int(switch_id), int(port_id), path))
    if not refs:
        raise FileNotFoundError('Data RRD agregat belum tersedia')
    args = ["rrdtool", "graph", "-", "--start", start, "--end", "now", "--title", str(title)[:80], "--vertical-label", "bits/sec", "--width", "800", "--height", "240"]
    in_names = []; out_names = []
    for idx, (_, _, path) in enumerate(refs):
        i = f"i{idx}"; o = f"o{idx}"; in_names.append(i); out_names.append(o)
        args += [f"DEF:{i}={path}:in:AVERAGE", f"DEF:{o}={path}:out:AVERAGE"]
    if len(in_names) > 1:
        in_expr = in_names[0] + ''.join(',' + x + ',+' for x in in_names[1:])
        out_expr = out_names[0] + ''.join(',' + x + ',+' for x in out_names[1:])
    else:
        in_expr = in_names[0]
        out_expr = out_names[0]
    args += [
        f"CDEF:isum={in_expr},8,*",
        f"CDEF:osum={out_expr},8,*",
        "CDEF:upload=osum,-1,*",
        "AREA:isum#16A34A:Download agregat",
        "AREA:upload#2563EB:Upload agregat",
        "HRULE:0#64748B"
    ]
    return _run(args, timeout=RRD_COMMAND_TIMEOUT, capture_output=True, check=True).stdout
