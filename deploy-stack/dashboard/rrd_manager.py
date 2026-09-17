import os, re, sqlite3, subprocess, sys, threading, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get("MIMBAR_DATA",ROOT/"data")).resolve(); RRD_DIR=DATA/"rrd"; DB_PATH=DATA/"mimbar.sqlite3"
_collector_thread=None; _collector_lock=threading.Lock()
def init_rrd_dir(): RRD_DIR.mkdir(parents=True,exist_ok=True)
def get_rrd_path(switch_id,port_id): init_rrd_dir(); return RRD_DIR/f"port_{int(switch_id)}_{int(port_id)}.rrd"
def ensure_rrd(switch_id,port_id):
 p=get_rrd_path(switch_id,port_id)
 if not p.exists(): subprocess.run(["rrdtool","create",str(p),"--start",str(int(time.time())-300),"--step","300","DS:in:DERIVE:600:0:U","DS:out:DERIVE:600:0:U","RRA:AVERAGE:0.5:1:576"],check=True)
 return p
def update_rrd(switch_id,port_id,bytes_in,bytes_out,timestamp=None): subprocess.run(["rrdtool","update",str(ensure_rrd(switch_id,port_id)),f"{'N' if timestamp is None else int(timestamp)}:{int(bytes_in)}:{int(bytes_out)}"],check=True)
def generate_graph_png(switch_id,port_id,start="-48h"):
 p=ensure_rrd(switch_id,port_id); return subprocess.run(["rrdtool","graph","-","--start",start,"--end","now","--title",f"Utilisasi Port {port_id}","--vertical-label","bits/sec","--width","600","--height","200","--lower-limit","0",f"DEF:i={p}:in:AVERAGE",f"DEF:o={p}:out:AVERAGE","CDEF:ib=i,8,*","CDEF:ob=o,8,*","AREA:ib#16A34A:Inbound","LINE1:ob#2563EB:Outbound"],capture_output=True,check=True).stdout
def fetch_rrd_data(switch_id,port_id,start="-48h"):
 p=ensure_rrd(switch_id,port_id); out=subprocess.run(["rrdtool","fetch",str(p),"AVERAGE","--start",start,"--end","now"],capture_output=True,text=True,check=True).stdout; result=[]
 for line in out.splitlines()[2:]:
  m=re.match(r"\s*(\d+):\s+(\S+)\s+(\S+)",line)
  if not m: continue
  def val(x):
   try: return round(float(x)*8,2)
   except ValueError: return 0.0
  result.append({'timestamp':int(m[1]),'in_bps':val(m[2]),'out_bps':val(m[3])})
 return result
def _inventory():
 if not DB_PATH.exists(): return []
 with sqlite3.connect(DB_PATH,timeout=10) as c:
  c.row_factory=sqlite3.Row
  return [dict(x) for x in c.execute("SELECT s.id switch_id,s.ip,s.community,p.id port_id,p.port_number ifindex FROM switches s JOIN ports p ON p.switch_id=s.id WHERE p.port_number GLOB '[0-9]*' AND p.port_number NOT GLOB '*[^0-9]*'")]
def _values(stdout):
 vals=[]
 for line in stdout.splitlines():
  m=re.search(r"(?:Counter32|Counter64|INTEGER|Gauge32):\s*(\d+)\s*$",line); vals.append(int(m[1])) if m else None
 return vals
def poll_snmp_once():
 for x in _inventory():
  base=["snmpget","-v2c","-c",x['community'],"-t","2","-r","1",x['ip']]; n=x['ifindex']
  try:
   hc=base+[f"1.3.6.1.2.1.31.1.1.1.6.{n}",f"1.3.6.1.2.1.31.1.1.1.10.{n}"]; z=subprocess.run(hc,capture_output=True,text=True)
   if z.returncode or len(_values(z.stdout))!=2: z=subprocess.run(base+[f"1.3.6.1.2.1.2.2.1.10.{n}",f"1.3.6.1.2.1.2.2.1.16.{n}"],capture_output=True,text=True)
   vals=_values(z.stdout)
   if z.returncode==0 and len(vals)==2: update_rrd(x['switch_id'],x['port_id'],*vals)
  except Exception as e: print(f"RRD poll gagal switch={x['switch_id']} port={x['port_id']}: {type(e).__name__}",file=sys.stderr)
def start_background_collector(interval_sec=300):
 global _collector_thread
 with _collector_lock:
  if _collector_thread is not None and _collector_thread.is_alive(): return False
  def loop():
   while True: poll_snmp_once(); time.sleep(interval_sec)
  _collector_thread=threading.Thread(target=loop,name='rrd-collector',daemon=True); _collector_thread.start(); return True
