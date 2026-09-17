#!/usr/bin/env python3
"""Local ARouteServer control plane. No production action happens at startup."""
import argparse
import concurrent.futures
from contextlib import contextmanager
import hashlib
import difflib
import hmac
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import threading
import tempfile
import time
import urllib.request
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import yaml
import onboarding
import rrd_manager

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('MIMBAR_DATA', ROOT / 'data')).resolve()
DB = DATA / 'mimbar.sqlite3'
SOURCE = Path(os.environ.get('MIMBAR_SOURCE', ROOT.parent)).resolve()
VERSION = '2.19.2'
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=2)
MUTEX = threading.RLock()
LOGIN_ATTEMPTS = {}

SYSLOG_COLLECTOR_URL = os.environ.get('SYSLOG_COLLECTOR_URL', 'http://syslog-analyzer:5514')
SYSLOG_COLLECTOR_TOKEN = os.environ.get('SYSLOG_COLLECTOR_TOKEN', 'analyzer-secret-token')

def syslog_proxy(handler, path):
    try:
        subpath = path.replace('/api/syslog', '', 1)
        if not subpath: subpath = '/summary'
        if subpath not in {'/summary','/logs','/events','/sources'}:
            return handler.response({'error':'Not found'},404)
        query_string = urlsplit(handler.path).query
        url = SYSLOG_COLLECTOR_URL + subpath + ('?' + query_string if query_string else '')
        req = urllib.request.Request(url, headers={'X-Syslog-Token': SYSLOG_COLLECTOR_TOKEN})
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode('utf-8'))
            handler.response(data, res.status)
    except urllib.error.HTTPError as e:
        handler.response({'error': 'Syslog request rejected'}, e.code if e.code in (400,404) else 502)
    except Exception:
        handler.response({'error': 'Syslog collector unavailable'}, 502)


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status

@contextmanager
def connect():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()

def query(sql, args=(), one=False):
    with connect() as c:
        cur = c.execute(sql, args)
        if cur.description:
            rows = [dict(x) for x in cur.fetchall()]
            return (rows[0] if rows else None) if one else rows
        return cur.lastrowid

def audit(kind, detail, actor='system'):
    query('INSERT INTO events(at,kind,detail,actor) VALUES(?,?,?,?)', (time.time(),kind,detail,actor))

def ixf_export():
    locs = query('SELECT code,name,source FROM locations ORDER BY code')
    nodes = {n['id']: n for n in query('SELECT id,name,location FROM nodes')}
    switches = query('SELECT id,name,ip,vendor,model,node_id,sys_name,sys_descr FROM switches ORDER BY id')
    ports = query('SELECT p.switch_id,p.member_asn,p.port_number,p.type,p.status,p.bandwidth,p.mac_address FROM ports p')
    # map ports by member asn, prefer ports with mac_address
    member_ports = {}
    for p in ports:
        member_ports.setdefault(p['member_asn'], []).append(p)

    # Build switch list
    switch_list = []
    for sw in switches:
        node = nodes.get(sw.get('node_id'), {})
        loc_code = node.get('location', '')
        # Infer software from sys_descr
        software = ''
        if sw.get('sys_descr'):
            software = sw['sys_descr']
        switch_list.append({
            "id": sw['id'],
            "name": sw.get('name') or sw.get('sys_name') or 'Switch',
            "colo": node.get('name', loc_code),
            "city": loc_code,
            "country": "ID",
            "manufacturer": sw.get('vendor', ''),
            "model": sw.get('model', '') or None,
            "software": software
        })

    # Build member list from clients.yml per location
    member_list = []
    seen_asn = set()
    for loc in locs:
        row = query('SELECT clients FROM locations WHERE code=?', (loc['code'],), one=True)
        if not row: continue
        clients = yaml.safe_load(row['clients'])
        if not isinstance(clients, dict) or 'clients' not in clients:
            continue
        for p in clients['clients']:
            asn = int(p['asn'])
            if asn in seen_asn: continue
            seen_asn.add(asn)
            cfg = p.get('cfg', {})
            as_sets = cfg.get('as_sets', {})
            as_macro = as_sets.get('ipv4') or as_sets.get('ipv6') or ''
            member = {
                "asnum": asn,
                "member_since": "2020-01-01T00:00:00Z",
                "url": p.get('website', ''),
                "name": p.get('description', ''),
                "peering_policy": "open",
                "member_type": "peering",
                "connection_list": []
            }
            ips = p['ip'] if isinstance(p['ip'], list) else [p['ip']]
            for ip in ips:
                fam = 4 if '.' in ip else 6
                # Find port assignment
                if_list = []
                for port in member_ports.get(asn, []):
                    # find switch
                    sw = next((sw for sw in switches if sw['id'] == port['switch_id']), None)
                    if sw:
                        speed_num = None
                        try:
                            # parse bandwidth like '1 Gbps', '10G', '10000'
                            import re
                            m = re.search(r'(\d+)', port.get('bandwidth', ''))
                            if m: speed_num = int(m.group(1))
                            if 'G' in (port.get('bandwidth', '') or '').upper():
                                speed_num = (speed_num or 1) * 1000
                        except Exception:
                            pass
                        if_list.append({
                            "switch_id": sw['id'],
                            "if_speed": speed_num or 1000
                        })
                vlan = {"vlan_id": 1}
                mac_addresses = []
                for port in member_ports.get(asn, []):
                    if port.get('mac_address'):
                        mac_addresses.append(port['mac_address'])
                addr_block = {
                    "address": ip,
                    "routeserver": True,
                    "mac_addresses": mac_addresses,
                    "max_prefix": 1000 if fam == 4 else 200
                }
                if as_macro:
                    addr_block['as_macro'] = as_macro
                if fam == 4:
                    vlan['ipv4'] = addr_block
                else:
                    vlan['ipv6'] = addr_block
                conn = {
                    "ixp_id": 1,
                    "state": "active",
                    "if_list": if_list,
                    "vlan_list": [vlan]
                }
                member['connection_list'].append(conn)
            member_list.append(member)

    return {
        "version": "1.0",
        "generator": "Mimbar IXP Dashboard",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ixp_list": [{
            "shortname": "IIX-JI",
            "name": "IIX Jawa Timur",
            "country": "ID",
            "url": "https://iix.net.id/",
            "ixf_id": 111,
            "ixp_id": 1,
            "support_email": "tiket@apjii.or.id",
            "support_phone": "+62**********",
            "peering_policy_list": ["open", "selective", "mandatory", "closed"],
            "vlan": [],
            "switch": switch_list
        }],
        "member_list": member_list
    }


def init():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    with connect() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY CHECK(id=1),name TEXT NOT NULL,salt TEXT NOT NULL,password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,csrf TEXT NOT NULL,expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS locations(code TEXT PRIMARY KEY,name TEXT NOT NULL,source TEXT NOT NULL,general TEXT NOT NULL,clients TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS machines(id TEXT PRIMARY KEY,location TEXT NOT NULL,name TEXT NOT NULL,host TEXT NOT NULL,router_id TEXT NOT NULL,ssh_user TEXT NOT NULL DEFAULT 'root',ssh_port INTEGER NOT NULL DEFAULT 22,status TEXT NOT NULL DEFAULT 'unverified',bird_version TEXT,checked_at REAL,revision INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,machine TEXT NOT NULL,location TEXT NOT NULL,revision INTEGER NOT NULL,machine_revision INTEGER NOT NULL,status TEXT NOT NULL,created REAL NOT NULL,log TEXT NOT NULL DEFAULT '',config TEXT,sha256 TEXT,validated_sha TEXT,validated_version TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,at REAL NOT NULL,kind TEXT NOT NULL,detail TEXT NOT NULL,actor TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS iixji_members(id INTEGER PRIMARY KEY,asn INTEGER,name TEXT,type TEXT,status TEXT,contact TEXT,notes TEXT,created REAL);
        CREATE INDEX IF NOT EXISTS idx_jobs_machine_status ON jobs(machine,status);
        CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created);
        CREATE TABLE IF NOT EXISTS member_applications(id TEXT PRIMARY KEY,created REAL NOT NULL,asn INTEGER NOT NULL,organization TEXT NOT NULL,email TEXT NOT NULL,location TEXT NOT NULL,peering_ipv4 TEXT,peering_ipv6 TEXT,ipv4_prefixes TEXT,ipv6_prefixes TEXT,bandwidth TEXT NOT NULL,domain TEXT NOT NULL,pairing_code TEXT NOT NULL,pairing_verified INTEGER NOT NULL DEFAULT 0,pairing_verified_at REAL);
        CREATE TABLE IF NOT EXISTS nodes(id INTEGER PRIMARY KEY,location TEXT NOT NULL REFERENCES locations(code),name TEXT NOT NULL,created REAL NOT NULL DEFAULT (strftime('%s','now')));
        CREATE TABLE IF NOT EXISTS switches(id INTEGER PRIMARY KEY,node_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,name TEXT NOT NULL,ip TEXT NOT NULL,community TEXT NOT NULL,vendor TEXT,model TEXT,sys_name TEXT,sys_descr TEXT,created REAL NOT NULL DEFAULT (strftime('%s','now')));
        CREATE TABLE IF NOT EXISTS ports(id INTEGER PRIMARY KEY,switch_id INTEGER NOT NULL REFERENCES switches(id) ON DELETE CASCADE,member_asn INTEGER NOT NULL,port_number TEXT NOT NULL,type TEXT NOT NULL,status TEXT NOT NULL,bandwidth TEXT NOT NULL,UNIQUE(switch_id,port_number));
        PRAGMA optimize;
        ''')
        try:
            c.execute('ALTER TABLE member_applications ADD COLUMN telegram_code TEXT')
        except sqlite3.OperationalError:
            pass
        c.execute('CREATE TABLE IF NOT EXISTS member_telegram_chats(asn INTEGER, chat_id INTEGER, PRIMARY KEY(asn, chat_id))')
        try:
            c.execute('ALTER TABLE ports ADD COLUMN mac_address TEXT')
        except sqlite3.OperationalError:
            pass
        try:
            c.execute('ALTER TABLE machines ADD COLUMN ssh_key TEXT')
        except sqlite3.OperationalError:
            pass
        if not c.execute('SELECT 1 FROM locations').fetchone():
            for code,name in [('SUB','Surabaya'),('AG','Tulungagung')]:
                p = SOURCE / ('arouteserver-'+code.lower())
                c.execute('INSERT INTO locations(code,name,source,general,clients) VALUES(?,?,?,?,?)',(code,name,code.lower(),(p/'general.yml').read_text(),(p/'clients.yml').read_text()))
            for mid,loc,name,host in [('sub-rs2','SUB','RS2 Surabaya','103.19.76.2'),('sub-rs3','SUB','RS3 Surabaya','103.19.76.3'),('ag-rs1','AG','RS AG Tulungagung','103.19.76.14')]:
                c.execute('INSERT INTO machines(id,location,name,host,router_id) VALUES(?,?,?,?,?)',(mid,loc,name,host,host))
            c.execute('INSERT INTO events(at,kind,detail,actor) VALUES(?,?,?,?)',(time.time(),'import','Arsip SUB dan AG diimpor. Status mesin belum diperiksa.','system'))
        c.execute("UPDATE jobs SET status='interrupted',log=log || '\nProses terhenti saat layanan restart; periksa mesin jika deployment sedang berlangsung.' WHERE status IN ('generating','validating','deploying')")
        c.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))

    init_accounts()
    onboarding.init_db(connect)

def init_accounts():
    """Upgrade the original single-admin schema, retaining password hashes."""
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        columns={r['name'] for r in c.execute('PRAGMA table_info(users)')}
        if 'role' not in columns:
            c.execute("CREATE TABLE users_multi(id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE,salt TEXT NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'super-admin' CHECK(role='super-admin'))")
            c.execute("INSERT INTO users_multi(id,name,salt,password) SELECT id,name,salt,password FROM users")
            c.execute('DROP TABLE users')
            c.execute('ALTER TABLE users_multi RENAME TO users')
        session_columns={r['name'] for r in c.execute('PRAGMA table_info(sessions)')}
        if 'user_id' not in session_columns:
            # Old sessions did not identify their owner; require a fresh login.
            c.execute('DELETE FROM sessions')
            c.execute('ALTER TABLE sessions ADD COLUMN user_id INTEGER REFERENCES users(id)')

def create_super_admin(name,password):
    name=name.strip()
    if not 2<=len(name)<=64 or not 12<=len(password)<=256:
        raise Problem('Gunakan nama 2–64 karakter dan password 12–256 karakter.')
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),310000).hex()
    return query("INSERT INTO users(name,salt,password,role) VALUES(?,?,?,'super-admin')",(name,salt,digest))


def get_location(code):
    loc = query('SELECT * FROM locations WHERE code=?',(code,),True)
    if not loc: raise Problem('Lokasi tidak ditemukan.',404)
    return loc

def get_machine(mid):
    m = query('SELECT * FROM machines WHERE id=?',(mid,),True)
    if not m: raise Problem('Mesin tidak ditemukan.',404)
    return m

def get_job(jid):
    j = query('SELECT * FROM jobs WHERE id=?',(jid,),True)
    if not j: raise Problem('Build tidak ditemukan.',404)
    return j

def parsed(general, clients):
    try:
        g, c = yaml.safe_load(general), yaml.safe_load(clients)
        if not isinstance(g,dict) or not isinstance(g.get('cfg'),dict): raise ValueError('general.yml wajib memiliki cfg.')
        if not isinstance(c,dict) or not isinstance(c.get('clients'),list): raise ValueError('clients.yml wajib memiliki daftar clients.')
        cfg = g['cfg']
        if not 1 <= int(cfg['rs_as']) <= 4294967295: raise ValueError('ASN tidak valid.')
        ipaddress.IPv4Address(cfg['router_id'])
        ips = set()
        for peer in c['clients']:
            if not isinstance(peer,dict) or not 1 <= int(peer['asn']) <= 4294967295: raise ValueError('ASN peer tidak valid.')
            for ip in peer['ip'] if isinstance(peer['ip'],list) else [peer['ip']]:
                ip = str(ipaddress.ip_address(ip))
                if ip in ips: raise ValueError('IP peer duplikat: '+ip)
                ips.add(ip)
        return g,c
    except (yaml.YAMLError,ValueError,TypeError,KeyError) as e: raise Problem('Konfigurasi tidak valid: '+str(e))

def peers_for(loc):
    inventory={r['member_asn']:r for r in query('SELECT ports.member_asn,ports.port_number AS port,ports.bandwidth,switches.name AS switch FROM ports JOIN switches ON switches.id=ports.switch_id ORDER BY ports.id')}
    rows = []
    for c in yaml.safe_load(loc['clients'])['clients']:
        for ip in c['ip'] if isinstance(c['ip'],list) else [c['ip']]:
            row={'asn':c['asn'],'ip':ip,'description':c.get('description',''),'family':ipaddress.ip_address(ip).version,'source':'YAML','community':', '.join(c.get('cfg',{}).get('attach_custom_communities',[]))};row.update(inventory.get(int(c['asn']),{}));rows.append(row)
    p = SOURCE / ('arouteserver-'+loc['source']) / 'templates/bird'
    main = (p/'main.j2').read_text()
    for f in re.findall(r'include "(ji-[\w.-]+\.j2)"', main):
        txt = (p/f).read_text()
        names = re.findall(r'description "([^"]+)"',txt)
        for idx,(ip,asn) in enumerate(re.findall(r'neighbor\s+(\S+)\s+as\s+(\d+)',txt)):
            row={'asn':int(asn),'ip':ip,'description':names[idx] if idx<len(names) else f,'family':ipaddress.ip_address(ip).version,'source':f,'community':'Template khusus'};row.update(inventory.get(int(asn),{}));rows.append(row)
    return rows

def generator():
    return os.environ.get('MIMBAR_AROUTESERVER') or (str(ROOT/'.venv/bin/arouteserver') if (ROOT/'.venv/bin/arouteserver').exists() else shutil.which('arouteserver'))

def validate_schema(general,clients):
    cli=generator()
    if not cli:return
    with tempfile.TemporaryDirectory(prefix='mimbar-schema-') as tmp:
        p=Path(tmp)
        (p/'general.yml').write_text(general);(p/'clients.yml').write_text(clients)
        shutil.copy2(SOURCE/'arouteserver-ag/log.ini',p/'log.ini')
        (p/'cache').mkdir()
        (p/'arouteserver.yml').write_text(yaml.safe_dump({'cfg_dir':tmp,'check_new_release':False,'templates_dir':str(SOURCE/'arouteserver-ag/templates'),'cfg_bogons':str(SOURCE/'arouteserver-ag/bogons.yml')}))
        run([cli,'check-config','--cfg',str(p/'arouteserver.yml'),'--logging-level','ERROR'],timeout=30)

def capabilities():
    return {'target':VERSION,'generator':bool(generator()),'validator':os.environ.get('MIMBAR_VALIDATOR','disabled'),'deploy_enabled':os.environ.get('MIMBAR_ALLOW_DEPLOY')=='1','ssh_configured':bool(os.environ.get('MIMBAR_SSH_KEY')),'snapshot_validation':json.loads((ROOT/'data/probes/validator-report.json').read_text()) if (ROOT/'data/probes/validator-report.json').is_file() else []}

def summary():
    locs = []
    for loc in query('SELECT * FROM locations ORDER BY code DESC'):
        ps = peers_for(loc); cfg = yaml.safe_load(loc['general'])['cfg']; filt=cfg.get('filtering',{})
        locs.append({'code':loc['code'],'name':loc['name'],'revision':loc['revision'],'asn':cfg['rs_as'],'peers':len(ps),'yaml_peers':sum(p['source']=='YAML' for p in ps),'custom_peers':sum(p['source']!='YAML' for p in ps),'asns':len(set(p['asn'] for p in ps)),'v4':sum(p['family']==4 for p in ps),'v6':sum(p['family']==6 for p in ps),'rpki':filt.get('rpki_bgp_origin_validation',{}).get('enabled',False),'irr':filt.get('irrdb',{}).get('enforce_prefix_in_as_set',True),'path_hiding':cfg.get('path_hiding',True)})
    machines = query('SELECT * FROM machines ORDER BY location DESC,name')
    for m in machines: m['has_ssh_key'] = bool(m.pop('ssh_key', None))
    return {'locations':locs,'machines':machines,'jobs':query('SELECT id,machine,location,revision,machine_revision,status,created,log,sha256,validated_sha,validated_version FROM jobs ORDER BY created DESC LIMIT 30'),'events':query('SELECT * FROM events ORDER BY id DESC LIMIT 60'),'capabilities':capabilities()}

def review_member(rid, data, actor):
    request=query('SELECT * FROM member_requests WHERE id=?',(rid,),True)
    if not request:raise Problem('Pengajuan tidak ditemukan.',404)
    if request['status']!='pending':raise Problem('Pengajuan sudah ditinjau.',409)
    action=data.get('decision')
    if action not in ('approve','reject'):raise Problem('Keputusan tidak valid.')
    member=json.loads(request['data']);reason=str(data.get('reason','')).strip()
    if len(reason)>1000:raise Problem('Catatan maksimal 1000 karakter.')
    if action=='reject' and not reason:raise Problem('Isi alasan penolakan agar member dapat memperbaiki pengajuan.')
    clients=None;loc=None
    if action=='approve':
        if data.get('verified') is not True:raise Problem('Verifikasi kewenangan ASN/prefix dan alokasi IP peering terlebih dahulu.')
        loc=get_location(member['location'])
        if data.get('revision')!=loc['revision']:raise Problem('Draft lokasi berubah. Buka kembali pengajuan.',409)
        g,c=parsed(loc['general'],loc['clients']);ips=[]
        for af in ('4','6'):
            value=str(data.get('peering'+af,member.get('peering'+af,''))).strip()
            if value:
                ip=onboarding.validate('peering'+af,value,member,{loc['code']:loc['name']})
                if ip:ips.append(ip)
        if not ips:raise Problem('Isi minimal satu IP peering LAN yang sudah dialokasikan.')
        existing={str(ipaddress.ip_address(p['ip'])) for p in peers_for(loc)}
        if any(ip in existing for ip in ips):raise Problem('IP peering sudah ada pada YAML atau template lokasi.')
        community=str(data.get('community','')).strip()
        if community and community not in g['cfg'].get('custom_communities',{}):raise Problem('Community lokasi tidak dikenal.')
        for ip in ips:
            peer={'asn':member['asn'],'ip':ip,'description':member['organization']}
            cfg={}
            if member['as_sets']:cfg['filtering']={'irrdb':{'as_sets':member['as_sets']}}
            if community:cfg['attach_custom_communities']=[community]
            if cfg:peer['cfg']=cfg
            c['clients'].append(peer)
        clients=yaml.safe_dump(c,sort_keys=False)
        parsed(loc['general'],clients);validate_schema(loc['general'],clients)
        for af in ('4','6'):member['approved_peering'+af]=next((ip for ip in ips if ipaddress.ip_address(ip).version==int(af)),'')
    status='approved' if action=='approve' else 'rejected'
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        cur=con.execute("UPDATE member_requests SET status=?,reviewed=?,reviewer=?,reason=?,revision=?,data=? WHERE id=? AND status='pending'",(status,time.time(),actor,reason,loc['revision']+1 if loc else None,json.dumps(member),rid))
        if not cur.rowcount:raise Problem('Pengajuan sudah ditinjau oleh sesi lain.',409)
        if loc:
            cur=con.execute('UPDATE locations SET clients=?,revision=revision+1 WHERE code=? AND revision=?',(clients,loc['code'],loc['revision']))
            if not cur.rowcount:raise Problem('Draft berubah. Buka kembali pengajuan.',409)
        con.execute('INSERT INTO events(at,kind,detail,actor) VALUES(?,?,?,?)',(time.time(),'member','#'+rid+' '+status+' / '+member['location'],actor))
        if request['chat_id'] is not None:
            message='Pengajuan #'+rid+(' diterima ke draft '+member['location']+'. Konfigurasi masih perlu build, validasi, dan deploy. Ini belum berarti sesi BGP aktif.' if loc else ' ditolak. Silakan perbaiki dan ajukan kembali melalui /daftar.')
            if reason:message+='\nCatatan admin: '+reason
            onboarding.enqueue(con,request['chat_id'],message)
    return {'ok':True,'status':status}


def clean_domain(v):
    d=str(v or '').strip().lower().rstrip('.')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+',d): raise Problem('Domain tidak valid.')
    return d

def web_application_to_member_data(row, extra=None):
    extra=extra or {}
    def split_prefixes(value):
        vals=[]
        for item in re.split(r'[\s,]+',str(value or '').strip()):
            if item:
                vals.append(str(ipaddress.ip_network(item,strict=False)))
        return list(dict.fromkeys(vals))
    as_sets=[]
    for item in re.split(r'[\s,]+',str(extra.get('as_sets') or row.get('as_sets') or '').upper().strip()):
        if item: as_sets.append(item)
    return {
        'location':row['location'],
        'organization':row['organization'],
        'asn':int(row['asn']),
        'prefix4':split_prefixes(row.get('ipv4_prefixes')),
        'prefix6':split_prefixes(row.get('ipv6_prefixes')),
        'as_sets':list(dict.fromkeys(as_sets)),
        'peering4':str(row.get('peering_ipv4') or ''),
        'peering6':str(row.get('peering_ipv6') or ''),
        'contact':str(extra.get('contact') or row.get('contact') or row['email']),
        'email':row['email'],
    }


def create_member_application(d):
    asn=int(d.get('asn'))
    if not 1<=asn<=4294967295: raise Problem('ASN tidak valid.')
    org=str(d.get('organization') or d.get('org') or '').strip()
    email=str(d.get('email') or d.get('contact') or d.get('noc_email') or '').strip().lower()
    loc=get_location(str(d.get('location','')).upper().strip())
    if not 2<=len(org)<=160 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email): raise Problem('Data organisasi/email tidak valid.')
    domain_part = email.split('@')[-1] if '@' in email else ''
    if domain_part in ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com']: raise Problem('Domain email tidak diizinkan. Harap gunakan email domain resmi.')
    p4=str(ipaddress.ip_address(d['peering_ipv4'])) if d.get('peering_ipv4') else ''
    p6=str(ipaddress.ip_address(d['peering_ipv6'])) if d.get('peering_ipv6') else ''
    if p4 and ipaddress.ip_address(p4).version!=4: raise Problem('IPv4 peering tidak valid.')
    if p6 and ipaddress.ip_address(p6).version!=6: raise Problem('IPv6 peering tidak valid.')
    prefixes=[]
    for key in ('ipv4_prefixes','ipv6_prefixes'):
        raw=str(d.get(key,'')).replace(',', '\n')
        vals=[]
        for x in raw.split():
            net=ipaddress.ip_network(x,strict=False); vals.append(str(net))
        prefixes.append('\n'.join(vals))
    bw=str(d.get('bandwidth','')).strip()
    if not re.fullmatch(r'[0-9]{1,5}\s*(M|G|T|Mbps|Gbps|Tbps)',bw,re.I): raise Problem('Bandwidth tidak valid.')
    domain=clean_domain(d.get('domain'))
    code='mimbar-'+secrets.token_hex(12); rid=secrets.token_hex(5)
    tcode = str(secrets.randbelow(900000) + 100000)
    created=time.time()
    query('INSERT INTO member_applications(id,created,asn,organization,email,location,peering_ipv4,peering_ipv6,ipv4_prefixes,ipv6_prefixes,bandwidth,domain,pairing_code,telegram_code) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid,created,asn,org,email,loc['code'],p4,p6,prefixes[0],prefixes[1],bw,domain,code,tcode))
    row={'id':rid,'created':created,'asn':asn,'organization':org,'email':email,'location':loc['code'],'peering_ipv4':p4,'peering_ipv6':p6,'ipv4_prefixes':prefixes[0],'ipv6_prefixes':prefixes[1],'bandwidth':bw,'domain':domain,'pairing_code':code,'telegram_code':tcode}
    member=web_application_to_member_data(row,d)
    query('INSERT OR IGNORE INTO member_requests(id,chat_id,user_id,username,data,created,origin,application_id) VALUES(?,?,?,?,?,?,?,?)',(rid,None,None,'web',json.dumps(member),created,'web',rid))

    smtp_host = os.environ.get('MIMBAR_SMTP_HOST')
    if smtp_host:
        try:
            import smtplib
            from email.message import EmailMessage
            msg = EmailMessage()
            msg['Subject'] = 'Kode Pairing Telegram IXP'
            msg['From'] = os.environ.get('MIMBAR_SMTP_FROM', 'no-reply@mimbar.ixp')
            msg['To'] = email

            msg.set_content(f'Kode pairing Telegram Anda adalah: {tcode}\n\nSilakan ketik /pairing {tcode} ke bot Telegram untuk mendapatkan notifikasi.')
            smtp_port = int(os.environ.get('MIMBAR_SMTP_PORT', '587'))
            with smtplib.SMTP(smtp_host, smtp_port) as s:
                smtp_user = os.environ.get('MIMBAR_SMTP_USER')
                smtp_pass = os.environ.get('MIMBAR_SMTP_PASS')
                if smtp_user and smtp_pass:
                    s.starttls()
                    s.login(smtp_user, smtp_pass)
                s.send_message(msg)
        except Exception as e:
            print(f'Gagal kirim SMTP: {e}')
    else:
        print(f'SMTP tidak dikonfigurasi. Kode pairing untuk {email}: {tcode}')
    return {'id':rid,'pairing_code':code,'txt_name':'_arouteserver-pairing.'+domain,'instruction':'Publish DNS TXT with pairing_code, then ask admin to verify.'}

def lookup_txt(name):
    if shutil.which('dig'):
        out=run(['dig','+short','TXT',name],timeout=10)
        return [x.strip().strip('"') for x in out.splitlines() if x.strip()]
    url='https://dns.google/resolve?name='+name+'&type=TXT'
    data=json.loads(urllib.request.urlopen(url,timeout=10).read().decode())
    return [''.join(s) if isinstance(s,list) else str(s) for a in data.get('Answer',[]) for s in [a.get('data','').replace('" "','').strip('"')]]

def verify_pairing(app_id,actor):
    row=query('SELECT * FROM member_applications WHERE id=?',(app_id,),one=True)
    if not row: raise Problem('Pengajuan tidak ditemukan.',404)
    values=lookup_txt('_arouteserver-pairing.'+row['domain'])
    ok=row['pairing_code'] in values
    if not ok: raise Problem('TXT pairing belum cocok.',409)
    query('UPDATE member_applications SET pairing_verified=1,pairing_verified_at=? WHERE id=?',(time.time(),app_id))
    audit('member_pairing','Pairing DNS verified for AS'+str(row['asn']),actor)
    return {'ok':True,'pairing_verified':True}


def sync_alice_now():
    try:
        subprocess.run([sys.executable, str(ROOT / "sync_alice.py")], cwd=str(ROOT), timeout=20, check=False)
    except Exception as e:
        audit("alice_lg", "Sinkronisasi AliceLG gagal: "+str(e)[:180])

def list_iixji_members():
    return query('SELECT * FROM iixji_members ORDER BY id DESC')

def create_iixji_member(d):
    asn = int(d.get('asn', 0)) if str(d.get('asn', '')).isdigit() else 0
    name = str(d.get('name', '')).strip()
    mtype = str(d.get('type', '')).strip()
    status = str(d.get('status', '')).strip()
    contact = str(d.get('contact', '')).strip()
    notes = str(d.get('notes', '')).strip()
    mid = query('INSERT INTO iixji_members(asn, name, type, status, contact, notes, created) VALUES(?,?,?,?,?,?,?)',
                (asn, name, mtype, status, contact, notes, time.time()))
    audit('iixji_member', 'Member IIX-JI '+name+' (AS'+str(asn)+') ditambahkan.')
    return {'success': True, 'id': mid}

def update_iixji_member(mid, d):
    row = query('SELECT * FROM iixji_members WHERE id=?', (mid,), True)
    if not row:
        raise Problem('Member IIX-JI tidak ditemukan.', 404)
    asn = int(d.get('asn', row['asn'])) if 'asn' in d and str(d.get('asn', '')).isdigit() else row['asn']
    name = str(d.get('name', row['name'])).strip()
    mtype = str(d.get('type', row['type'])).strip()
    status = str(d.get('status', row['status'])).strip()
    contact = str(d.get('contact', row['contact'])).strip()
    notes = str(d.get('notes', row['notes'])).strip()
    query('UPDATE iixji_members SET asn=?, name=?, type=?, status=?, contact=?, notes=? WHERE id=?',
          (asn, name, mtype, status, contact, notes, mid))
    audit('iixji_member', 'Member IIX-JI '+name+' (AS'+str(asn)+') diperbarui.')
    return {'success': True}

def delete_iixji_member(mid):
    row = query('SELECT * FROM iixji_members WHERE id=?', (mid,), True)
    if not row:
        raise Problem('Member IIX-JI tidak ditemukan.', 404)
    query('DELETE FROM iixji_members WHERE id=?', (mid,))
    audit('iixji_member', 'Member IIX-JI '+row['name']+' dihapus.')
    return {'success': True}

def list_nodes():
    return query('SELECT * FROM nodes ORDER BY location,name')

def create_node(d):
    loc=get_location(str(d.get('location','')).upper().strip())
    name=str(d.get('name','')).strip()
    if not 2<=len(name)<=80: raise Problem('Data node tidak valid.')
    nid=query('INSERT INTO nodes(location,name) VALUES(?,?)',(loc['code'],name))
    audit('node','Node '+name+' ditambahkan ke '+loc['code']+'.')
    return {'id':nid}

def list_switches():
    rows=query('''SELECT s.id, s.node_id, s.name, s.ip, s.vendor, s.model, s.sys_name, s.sys_descr, n.location 
                  FROM switches s JOIN nodes n ON s.node_id = n.id ORDER BY n.location, s.name''')
    ports=query('SELECT * FROM ports ORDER BY switch_id,port_number')
    by={r['id']:[] for r in rows}
    for p in ports: by.setdefault(p['switch_id'],[]).append(p)
    for r in rows: r['ports']=by.get(r['id'],[])
    return rows

def create_switch(d):
    try: node_id=int(d.get('node_id', 0))
    except (ValueError, TypeError): node_id=0
    node=query('SELECT * FROM nodes WHERE id=?', (node_id,), True)
    if not node: raise Problem('Node tidak ditemukan.', 400)
    name=str(d.get('name','')).strip(); ip=str(ipaddress.ip_address(d.get('ip',''))); community=str(d.get('community','')).strip()
    if not 2<=len(name)<=80 or not 1<=len(community)<=128: raise Problem('Data switch tidak valid.')
    sid=query('INSERT INTO switches(node_id,name,ip,community,vendor,model) VALUES(?,?,?,?,"","")',(node['id'],name,ip,community))
    audit('switch','Switch '+name+' ditambahkan ke node '+node['name']+'.')
    return {'id':sid}

def create_port(d):
    sw=query('SELECT id FROM switches WHERE id=?',(int(d.get('switch_id')),),one=True)
    if not sw: raise Problem('Switch tidak ditemukan.',404)
    asn=int(d.get('member_asn'))
    if not 1<=asn<=4294967295: raise Problem('ASN tidak valid.')
    vals=[str(d.get(k,'')).strip() for k in ('port_number','type','status','bandwidth')]
    if any(not v or len(v)>80 for v in vals): raise Problem('Data port tidak valid.')
    mac = str(d.get('mac_address', '')).strip()
    pid=query('INSERT INTO ports(switch_id,member_asn,port_number,type,status,bandwidth,mac_address) VALUES(?,?,?,?,?,?,?)',(sw['id'],asn,*vals,mac))
    return {'id':pid, 'mac_address': mac}

def assign_peer_port(asn, d):
    sw=query('SELECT id FROM switches WHERE id=?',(int(d.get('switch_id')),),one=True)
    if not sw: raise Problem('Switch tidak ditemukan.',404)
    if not 1<=asn<=4294967295: raise Problem('ASN tidak valid.')
    port_number=str(d.get('port_number','')).strip()
    status=str(d.get('status','')).strip()
    bandwidth=str(d.get('bandwidth','')).strip()
    if any(not v or len(v)>80 for v in (port_number,status,bandwidth)): raise Problem('Data port tidak valid.')
    if status not in ('up','down'): raise Problem('Status port tidak valid.')
    mac=str(d.get('mac_address','')).strip()
    if mac and not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}',mac): raise Problem('MAC address tidak valid.')
    existing=query('SELECT id,type FROM ports WHERE member_asn=?',(asn,),one=True)
    if existing:
        query('UPDATE ports SET switch_id=?,port_number=?,status=?,bandwidth=?,mac_address=? WHERE id=?',(sw['id'],port_number,status,bandwidth,mac,existing['id']))
        pid=existing['id']; physical_type=existing['type']
    else:
        physical_type='Belum terdeteksi'
        pid=query('INSERT INTO ports(switch_id,member_asn,port_number,type,status,bandwidth,mac_address) VALUES(?,?,?,?,?,?,?)',(sw['id'],asn,port_number,physical_type,status,bandwidth,mac))
    return {'id':pid,'port_number':port_number,'physical_type':physical_type,'bandwidth':bandwidth}

def infer_vendor_model(text):
    low=text.lower(); vendor=''; model=''
    for name in ['Juniper','Cisco','MikroTik','Huawei','Arista','HPE','Dell']:
        if name.lower() in low: vendor=name; break
    m=re.search(r'\b(EX\d+[\w-]*|QFX\d+[\w-]*|Nexus\s*\d+|CCR\d+[\w-]*|CRS\d+[\w-]*|S\d{4,5}[\w-]*)\b',text,re.I)
    if m: model=m.group(1)
    return vendor,model

def discover_switch(sid):
    sw=query('SELECT * FROM switches WHERE id=?',(sid,),one=True)
    if not sw: raise Problem('Switch tidak ditemukan.',404)
    # Community passed through env, not argv/logs.
    env={**os.environ,'SNMP_COMMUNITY':sw['community']}
    out=run(['sh','-c','snmpget -v2c -c "$SNMP_COMMUNITY" "$1" sysDescr.0 sysName.0','snmp-discover',sw['ip']],timeout=15,env=env)
    vendor,model=infer_vendor_model(out)
    sysname='';
    m=re.search(r'sysName\.0\s*=\s*(?:STRING:\s*)?(.+)',out)
    if m: sysname=m.group(1).strip()
    query('UPDATE switches SET vendor=?,model=?,sys_name=?,sys_descr=? WHERE id=?',(vendor,model,sysname,out[:2000],sid))
    return {'id':sid,'vendor':vendor,'model':model,'sys_name':sysname,'sys_descr':out[:2000]}

def run(args, timeout=30, **kw):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kw)
    except (OSError,subprocess.TimeoutExpired) as e: raise Problem(str(e),503)
    output = (result.stdout+'\n'+result.stderr).strip()
    if result.returncode: raise Problem(output[-16000:] or 'Perintah gagal.',422)
    return output

def update_job(jid,status,log,**fields):
    values = {'status':status,'log':log,**fields}
    query('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',tuple(values.values())+(jid,))

def generate_job(jid,loc,m,actor):
    try:
        cli = generator()
        if not cli: raise Problem('ARouteServer belum terpasang. Pasang requirements.txt terlebih dahulu.',503)
        work = DATA/'builds'/jid
        work.mkdir(parents=True)
        src = SOURCE/('arouteserver-'+loc['source'])
        g,c = parsed(loc['general'],loc['clients'])
        g['cfg']['router_id'] = m['router_id']
        # Clone inputs, including custom templates. Never mutate the source archives.
        for name in ['templates','cache']:
            shutil.copytree(src/name,work/name)
        for name in ['bogons.yml','log.ini']:
            shutil.copy2(src/name,work/name)
        (work/'general.yml').write_text(yaml.safe_dump(g,sort_keys=False))
        (work/'clients.yml').write_text(loc['clients'])
        opts = yaml.safe_load((src/'arouteserver.yml').read_text()) or {}
        opts['cfg_dir'] = str(work)
        opts['check_new_release'] = False
        opts['bgpq3_path'] = str(ROOT/'tools/bgpq4/usr/bin/bgpq4') if (ROOT/'tools/bgpq4/usr/bin/bgpq4').exists() else (shutil.which('bgpq4') or shutil.which('bgpq3') or 'bgpq4')
        opts['bgpq3_timeout'] = 20
        (work/'arouteserver.yml').write_text(yaml.safe_dump(opts))
        output = run([cli,'bird','--cfg',str(work/'arouteserver.yml'),'--target-version','2.16','--logging-level','WARNING','-o',str(work/'bird.conf')],timeout=600,cwd=work)
        config = (work/'bird.conf').read_text()
        digest = hashlib.sha256(config.encode()).hexdigest()
        update_job(jid,'generated','ARouteServer 1.23.2, profil sintaks BIRD 2.16. Target validator/deploy BIRD 2.19.2. Belum divalidasi.\n'+output,config=config,sha256=digest)
        audit('build','Build '+jid[:8]+' untuk '+m['name']+' selesai.',actor)
    except Exception as e:
        update_job(jid,'failed',str(e));audit('build_failed','Build '+jid[:8]+': '+str(e)[-500:],actor)

def validate_job(jid,actor):
    j=get_job(jid)
    try:
        if os.environ.get('MIMBAR_VALIDATOR')!='docker': raise Problem('Validator belum diaktifkan. Container BIRD 2.19.2 belum diuji pada server ini.',503)
        image=os.environ.get('MIMBAR_BIRD_IMAGE','mimbar-bird:2.19.2')
        common=['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','64','--memory','512m','--cpus','1','-i',image]
        version=run(common+['--version'])
        if not re.search(r'\b2\.19\.2\b',version): raise Problem('Versi validator tidak sesuai: '+version)
        # Input through stdin avoids Docker bind mounts and permits remote Docker daemons.
        result=run(common+['-p','-c','/dev/stdin'],timeout=60,input=j['config'])
        update_job(jid,'validated',version+'\nbird -p: konfigurasi lolos pemeriksaan parser.\n'+result,validated_sha=j['sha256'],validated_version=VERSION)
        audit('validation','Build '+jid[:8]+' lolos parser BIRD '+VERSION+'.',actor)
    except Exception as e:
        update_job(jid,'validation_failed',str(e),validated_sha=None,validated_version=None)
        audit('validation_failed','Build '+jid[:8]+': '+str(e)[-500:],actor)

def ssh_args(m):
    key=os.environ.get('MIMBAR_SSH_KEY')
    hosts=os.environ.get('MIMBAR_KNOWN_HOSTS')
    if m.get('ssh_key'):
        (DATA / 'keys').mkdir(exist_ok=True, mode=0o700)
        kf = DATA / 'keys' / (m['id'] + '.key')
        kf.write_text(m['ssh_key'])
        kf.chmod(0o600)
        key = str(kf)
    if not key or not hosts or not Path(key).is_file() or not Path(hosts).is_file():
        raise Problem('Atur MIMBAR_SSH_KEY dan MIMBAR_KNOWN_HOSTS pada server dashboard terlebih dahulu.',409)
    return ['ssh','-F','/dev/null','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8','-o','UserKnownHostsFile='+hosts,'-i',key,'-p',str(m['ssh_port']),m['ssh_user']+'@'+m['host']]

def check_machine(mid,actor):
    m=get_machine(mid)
    result=run(ssh_args(m)+['bird --version && sudo -n /usr/local/sbin/mimbar-deploy status'],timeout=25)
    ver=re.search(r'BIRD\s+(\d+\.\d+(?:\.\d+)?)',result)
    with connect() as c:
        cur=c.execute('UPDATE machines SET status=?,bird_version=?,checked_at=? WHERE id=? AND revision=?',('reachable',ver.group(1) if ver else None,time.time(),mid,m['revision']))
        if not cur.rowcount:raise Problem('Mesin berubah saat koneksi diperiksa. Ulangi pemeriksaan.',409)
    audit('connection',m['name']+': SSH dan BIRD merespons.',actor)
    return {'output':result}

SAFE_ID=re.compile(r'^[a-z0-9-]{2,64}$')
SAFE_LOC=re.compile(r'^[A-Z][A-Z0-9-]{1,7}$')
SAFE_VERSION=re.compile(r'^\d{8}T\d{6}Z-[a-f0-9]{12}$')

def _version_dir(machine,location):
    if not SAFE_ID.fullmatch(machine) or not SAFE_LOC.fullmatch(location):raise Problem('Path riwayat deployment tidak valid.',400)
    return DATA/'deployment-history'/location/machine

def _atomic_immutable_write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.link(tmp,path);os.unlink(tmp)
        os.chmod(path,0o440)
    except Exception:
        try:os.unlink(tmp)
        except FileNotFoundError:pass
        raise

def save_deployment_snapshot(machine,location,config,reason,source_id,actor):
    if not isinstance(config,str):raise Problem('Konfigurasi snapshot tidak valid.',400)
    digest=hashlib.sha256(config.encode()).hexdigest(); stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
    vid=stamp+'-'+secrets.token_hex(6); base=_version_dir(machine,location)/vid
    meta={'id':vid,'machine':machine,'location':location,'created':time.time(),'reason':reason,'source_id':source_id,'actor':actor,'sha256':digest}
    _atomic_immutable_write(base.with_suffix('.conf'),config.encode())
    try:_atomic_immutable_write(base.with_suffix('.json'),json.dumps(meta,sort_keys=True).encode())
    except Exception:
        base.with_suffix('.conf').unlink(missing_ok=True);raise
    return {**meta,'config_path':str(base.with_suffix('.conf'))}

def list_deployment_versions(machine,location):
    root=_version_dir(machine,location)
    rows=[]
    for f in root.glob('*.json') if root.exists() else []:
        if SAFE_VERSION.fullmatch(f.stem):
            try:rows.append(json.loads(f.read_text()))
            except (OSError,json.JSONDecodeError):pass
    return sorted(rows,key=lambda x:x['created'],reverse=True)

def get_deployment_version(machine,location,vid):
    if not SAFE_VERSION.fullmatch(vid):raise Problem('Versi deployment tidak valid.',400)
    root=_version_dir(machine,location); mp=root/(vid+'.json');cp=root/(vid+'.conf')
    if not mp.is_file() or not cp.is_file():raise Problem('Versi deployment tidak ditemukan.',404)
    meta=json.loads(mp.read_text());config=cp.read_text()
    if hashlib.sha256(config.encode()).hexdigest()!=meta['sha256']:raise Problem('Snapshot deployment rusak.',409)
    current=list_deployment_versions(machine,location)
    latest=get_deployment_version(machine,location,current[0]['id'])['config'] if current and current[0]['id']!=vid else config
    return {**meta,'config':config,'diff':''.join(difflib.unified_diff(latest.splitlines(True),config.splitlines(True),fromfile='current',tofile=vid))}

def rollback_deployment(machine,vid,confirmation,actor):
    with MUTEX:
        m=get_machine(machine); target=get_deployment_version(machine,m['location'],vid)
        if os.environ.get('MIMBAR_ALLOW_DEPLOY')!='1':raise Problem('Deployment belum diaktifkan oleh administrator server.',409)
        if confirmation!=m['name']:raise Problem('Nama konfirmasi tidak cocok.')
        if m['bird_version']!=VERSION or m['status']!='reachable' or (m['checked_at'] or 0)<time.time()-300:raise Problem('Periksa koneksi mesin dengan BIRD 2.19.2 dalam 5 menit sebelum rollback.',409)
        rows=list_deployment_versions(machine,m['location'])
        current=get_deployment_version(machine,m['location'],rows[0]['id'])['config']
        save_deployment_snapshot(machine,m['location'],current,'rollback_backup',vid,actor)
        args=ssh_args(m)+['sudo -n /usr/local/sbin/mimbar-deploy apply']
    def task():
        try:
            output=run(args,timeout=120,input=json.dumps({'config':target['config'],'sha256':target['sha256'],'version':VERSION}))
            if json.loads(output).get('status')!='deployed':raise Problem('Agent tidak mengonfirmasi rollback.')
            save_deployment_snapshot(machine,m['location'],target['config'],'rollback',vid,actor)
            audit('rollback',m['name']+': versi '+vid+' dipulihkan.',actor)
        except Exception as e:audit('rollback_failed',m['name']+': '+str(e)[-500:],actor)
    POOL.submit(task);return {'id':vid}

def deploy_job(jid,confirmation,actor):
    with MUTEX:
        j=get_job(jid);m=get_machine(j['machine']);loc=get_location(j['location'])
        if os.environ.get('MIMBAR_ALLOW_DEPLOY')!='1': raise Problem('Deployment belum diaktifkan oleh administrator server.',409)
        if j['status']!='validated' or j['validated_sha']!=j['sha256'] or j['validated_version']!=VERSION: raise Problem('Build wajib lolos validasi BIRD 2.19.2 sebelum deploy.',409)
        if j['sha256']!=hashlib.sha256(j['config'].encode()).hexdigest(): raise Problem('Checksum build berubah.',409)
        if loc['revision']!=j['revision'] or m['revision']!=j['machine_revision']: raise Problem('Konfigurasi atau mesin berubah. Buat build baru.',409)
        if confirmation!=m['name']: raise Problem('Nama konfirmasi tidak cocok.')
        if m['bird_version']!=VERSION or m['status']!='reachable' or (m['checked_at'] or 0)<time.time()-300: raise Problem('Periksa koneksi mesin dengan BIRD 2.19.2 dalam 5 menit sebelum deploy.',409)
        if query("SELECT 1 FROM jobs WHERE machine=? AND status='deploying'",(m['id'],),True): raise Problem('Mesin sedang menjalankan deployment lain.',409)
        save_deployment_snapshot(m['id'],m['location'],j['config'],'deploy',jid,actor)
        args=ssh_args(m)+['sudo -n /usr/local/sbin/mimbar-deploy apply']
        update_job(jid,'deploying','Mengirim konfigurasi untuk validasi ulang, backup, dan reload.')
    def task():
        try:
            payload=json.dumps({'config':j['config'],'sha256':j['sha256'],'version':VERSION})
            output=run(args,timeout=120,input=payload)
            response=json.loads(output)
            if response.get('status')!='deployed': raise Problem('Agent tidak mengonfirmasi deployment.')
            update_job(jid,'deployed',output)
            audit('deployment',m['name']+': build '+jid[:8]+' diterapkan.',actor)
        except Exception as e:
            update_job(jid,'deploy_failed','Deployment gagal atau status belum pasti. Periksa mesin dan log agent.\n'+str(e))
            audit('deployment_failed',m['name']+': '+str(e)[-500:],actor)
    POOL.submit(task)
    return {'id':jid}

class Handler(BaseHTTPRequestHandler):
    server_version='Mimbar/1.0'
    def log_message(self,*args): pass
    def response(self,data,status=200,cookie=None,ctype='application/json; charset=utf-8'):
        raw=json.dumps(data).encode() if ctype.startswith('application/json') else data
        self.send_response(status)
        self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','same-origin')
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(raw)
    def session(self,required=True):
        cookie=SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except Exception: pass
        token=cookie['mimbar_session'].value if 'mimbar_session' in cookie else ''
        s=query("SELECT sessions.*,users.name,users.role FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND expires>? AND users.role='super-admin'",(hashlib.sha256(token.encode()).hexdigest(),time.time()),True)
        if required and not s: raise Problem('Silakan masuk kembali.',401)
        return s
    def body(self):
        if 'application/json' not in self.headers.get('Content-Type',''):raise Problem('Content-Type wajib application/json.',415)
        try:n=int(self.headers.get('Content-Length','0'))
        except ValueError:raise Problem('Ukuran request tidak valid.')
        if n<0 or n>2_000_000:raise Problem('Ukuran maksimal request 2 MB.',413)
        if n == 0: return {}
        try:
            d=json.loads(self.rfile.read(n))
            if not isinstance(d,dict):raise ValueError()
            return d
        except (ValueError,UnicodeError):raise Problem('JSON tidak valid.')
    def cookie(self,token,age):
        return f'mimbar_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={age}'+('; Secure' if os.environ.get('MIMBAR_SECURE_COOKIE')=='1' else '')
    def do_GET(self):self.handle_request('GET')
    def do_POST(self):self.handle_request('POST')
    def do_PUT(self):self.handle_request('PUT')
    def do_DELETE(self):self.handle_request('DELETE')
    def handle_request(self,method):
        try:
            path=urlsplit(self.path).path
            if not path.startswith('/api/'):
                if method!='GET':
                    raise Problem('Tidak ditemukan.',404)
                if path=='/member-baru':
                    html=(ROOT/'dist'/'member-baru.html').read_bytes()
                    return self.response(html,ctype='text/html; charset=utf-8')
                files={'/':'index.html','/app.js':'app.js','/member-baru.js':'member-baru.js','/style.css':'style.css','/favicon.svg':'favicon.svg'}
                if path not in files: raise Problem('Tidak ditemukan.',404)
                p=ROOT/'dist'/files[path]
                return self.response(p.read_bytes(),ctype=mimetypes.guess_type(str(p))[0]+'; charset=utf-8')
            if method=='GET' and path=='/api/session':
                s=self.session(False);u=query('SELECT 1 FROM users LIMIT 1',one=True)
                return self.response({'setup':not bool(u),'user':s['name'] if s else None,'role':s['role'] if s else None,'csrf':s['csrf'] if s else None})
            if method=='GET' and path=='/api/ixf.json':
                return self.response(ixf_export())
            if method!='GET':
                origin=self.headers.get('Origin')
                host=self.headers.get('Host','')
                if origin and urlsplit(origin).netloc!=host: raise Problem('Origin tidak diizinkan.',403)
                d=self.body()
                if path in ['/api/setup','/api/login','/api/public/apply']:
                    return self.login(d,path=='/api/setup')
                if path=='/api/member-applications':
                    return self.response(create_member_application(d),201)
            s=self.session()
            if method!='GET' and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),s['csrf']): raise Problem('Token sesi tidak cocok. Muat ulang halaman.',403)
            actor=s['name']
            
            if method=='GET':
                if path=='/api/state':return self.response(summary())
                if path=='/api/members':return self.response(onboarding.listing(connect))
                if path=='/api/nodes':return self.response(list_nodes())
                if path=='/api/switches':return self.response(list_switches())
                match=re.fullmatch(r'/api/switches/(\d+)/ports/(\d+)/(data|graph)',path)
                if match:
                    sid,pid,kind=int(match[1]),int(match[2]),match[3]
                    port=query('SELECT 1 FROM ports WHERE id=? AND switch_id=?',(pid,sid),one=True)
                    if not port: raise Problem('Port tidak ditemukan.',404)
                    if kind=='data': return self.response(rrd_manager.fetch_rrd_data(sid,pid))
                    return self.response(rrd_manager.generate_graph_png(sid,pid),ctype='image/png')
                if path.startswith('/api/syslog'): return syslog_proxy(self, path)
                if path=='/api/iixji-members':return self.response(list_iixji_members())
                if path=='/api/ixf.json':return self.response(ixf_export())
                match=re.fullmatch(r'/api/locations/([A-Z0-9-]+)',path)
                if match:
                    loc=get_location(match[1]);cfg=yaml.safe_load(loc['general'])['cfg'];f=cfg.get('filtering',{})
                    policy={'rpki':f.get('rpki_bgp_origin_validation',{}).get('enabled',False),'irr_origin':f.get('irrdb',{}).get('enforce_origin_in_as_set',True),'irr_prefix':f.get('irrdb',{}).get('enforce_prefix_in_as_set',True),'path_hiding':cfg.get('path_hiding',True),'ipv4_min':f.get('ipv4_pref_len',{}).get('min',8),'ipv4_max':f.get('ipv4_pref_len',{}).get('max',24),'ipv6_min':f.get('ipv6_pref_len',{}).get('min',12),'ipv6_max':f.get('ipv6_pref_len',{}).get('max',48)}
                    return self.response({**loc,'peers':peers_for(loc),'policy':policy,'communities':list(cfg.get('custom_communities',{}))})
                match=re.fullmatch(r'/api/locations/([a-zA-Z0-9-]+)/templates',path)
                if match:
                    loc=get_location(match[1].upper());tdir=SOURCE/('arouteserver-'+loc['source'])/'templates'/'bird'
                    if not tdir.exists():return self.response([])
                    return self.response(sorted([f.name for f in tdir.iterdir() if f.is_file() and f.name.endswith('.j2')]))
                match=re.fullmatch(r'/api/locations/([a-zA-Z0-9-]+)/templates/([^/]+)',path)
                if match:
                    loc=get_location(match[1].upper());fname=match[2]
                    if not re.fullmatch(r'^[a-zA-Z0-9_.-]+\.j2$',fname):raise Problem('Template tidak ditemukan.',404)
                    tfile=SOURCE/('arouteserver-'+loc['source'])/'templates'/'bird'/fname
                    if not tfile.is_file():raise Problem('Template tidak ditemukan.',404)
                    return self.response({'content':tfile.read_text(encoding='utf-8')})
                match=re.fullmatch(r'/api/machines/([a-z0-9-]+)/deployments(?:/([0-9A-Fa-fTZ-]+))?',path)
                if match:
                    m=get_machine(match[1]);return self.response(get_deployment_version(m['id'],m['location'],match[2]) if match[2] else list_deployment_versions(m['id'],m['location']))
                match=re.fullmatch(r'/api/jobs/([a-f0-9]+)',path)
                if match:return self.response(get_job(match[1]))
            match=re.fullmatch(r'/api/members/([a-f0-9]{10})/review',path)
            if method=='POST' and match:return self.response(review_member(match[1],d,actor))
            match=re.fullmatch(r'/api/member-applications/([a-f0-9]{10})/verify-pairing',path)
            if method=='POST' and match:return self.response(verify_pairing(match[1],actor))
            if method=='POST' and path=='/api/nodes':return self.response(create_node(d),201)
            if method=='POST' and path=='/api/switches':return self.response(create_switch(d),201)
            if method=='POST' and path=='/api/ports':return self.response(create_port(d),201)
            if method=='POST' and path=='/api/iixji-members':return self.response(create_iixji_member(d),201)
            match=re.fullmatch(r'/api/iixji-members/(\d+)',path)
            if method=='PUT' and match:return self.response(update_iixji_member(int(match[1]),d))
            if method=='DELETE' and match:return self.response(delete_iixji_member(int(match[1])))
            match=re.fullmatch(r'/api/peers/(\d+)/assign',path)
            if method=='POST' and match:return self.response(assign_peer_port(int(match[1]),d))
            match=re.fullmatch(r'/api/switches/(\d+)/discover',path)
            if method=='POST' and match:return self.response(discover_switch(int(match[1])))
            match=re.fullmatch(r'/api/nodes/(\d+)',path)
            if method=='DELETE' and match:
                nid=int(match[1])
                node=query('SELECT name FROM nodes WHERE id=?',(nid,),True)
                if not node: raise Problem('Node tidak ditemukan.',404)
                query('DELETE FROM nodes WHERE id=?',(nid,))
                audit('node','Node '+node['name']+' dihapus.')
                return self.response({'ok':True})
            if method=='POST' and path=='/api/logout':
                query('DELETE FROM sessions WHERE token=?',(s['token'],));return self.response({'ok':True},cookie=self.cookie('',0))
            if method=='POST' and path=='/api/locations':
                code=str(d.get('code','')).upper().strip();name=str(d.get('name','')).strip()
                if not re.fullmatch(r'[A-Z][A-Z0-9-]{1,7}',code) or not 2<=len(name)<=80: raise Problem('Isi kode lokasi (2–8 karakter) dan nama kota.')
                # New locations use standard AG template with empty client list, never copy production peers.
                g=yaml.safe_load(get_location('AG')['general']);g['cfg']['router_id']='192.0.2.1'
                src_dir = SOURCE / f'arouteserver-{code.lower()}'
                if not src_dir.exists():
                    import shutil
                    shutil.copytree(SOURCE / 'arouteserver-ag', src_dir)
                query('INSERT INTO locations(code,name,source,general,clients) VALUES(?,?,?,?,?)',(code,name,code.lower(),yaml.safe_dump(g,sort_keys=False),'clients: []\n'))
                audit('location','Lokasi '+code+' / '+name+' ditambahkan.',actor);return self.response({'code':code},201)
            match=re.fullmatch(r'/api/locations/([A-Z0-9-]+)/(policy|peers)',path)
            if method=='POST' and match:
                loc=get_location(match[1]);g,c=parsed(loc['general'],loc['clients'])
                if d.get('revision')!=loc['revision']:raise Problem('Draft berubah. Muat ulang lokasi.',409)
                if match[2]=='policy':
                    filt=g['cfg'].setdefault('filtering',{})
                    for key in ['rpki','irr_origin','irr_prefix','path_hiding']:
                        if not isinstance(d.get(key),bool):raise Problem('Nilai kebijakan harus boolean.')
                    filt.setdefault('rpki_bgp_origin_validation',{})['enabled']=d['rpki']
                    filt.setdefault('irrdb',{})['enforce_origin_in_as_set']=d['irr_origin']
                    filt['irrdb']['enforce_prefix_in_as_set']=d['irr_prefix']
                    g['cfg']['path_hiding']=d['path_hiding']
                    for af,bound in [('ipv4',32),('ipv6',128)]:
                        mn,mx=int(d[af+'_min']),int(d[af+'_max'])
                        if not 0<=mn<=mx<=bound:raise Problem('Batas panjang prefix tidak valid.')
                        filt[af+'_pref_len']={'min':mn,'max':mx}
                else:
                    if d.get('remove_ip'):
                        ip=str(ipaddress.ip_address(d['remove_ip']))
                        updated=[];found=False
                        for peer in c['clients']:
                            ips=peer['ip'] if isinstance(peer['ip'],list) else [peer['ip']]
                            keep=[x for x in ips if str(ipaddress.ip_address(x))!=ip]
                            if len(keep)!=len(ips):found=True
                            if keep:updated.append({**peer,'ip':keep if isinstance(peer['ip'],list) else keep[0]})
                        if not found:raise Problem('Peer YAML tidak ditemukan.',404)
                        c['clients']=updated
                    else:
                        ip=str(ipaddress.ip_address(d['ip']));asn=int(d['asn']);description=str(d.get('description','')).strip()
                        if not description or len(description)>160:raise Problem('Isi nama peer maksimal 160 karakter.')
                        peer={'asn':asn,'ip':ip,'description':description}
                        community=str(d.get('community','')).strip()
                        if community:
                            if community not in g['cfg'].get('custom_communities',{}):raise Problem('Community tidak terdaftar pada lokasi ini.')
                            peer['cfg']={'attach_custom_communities':[community]}
                        if any(p['ip']==ip for p in peers_for(loc)):raise Problem('IP sudah terdaftar pada YAML atau template.')
                        c['clients'].append(peer)
                general,clients=yaml.safe_dump(g,sort_keys=False),yaml.safe_dump(c,sort_keys=False)
                parsed(general,clients)
                validate_schema(general,clients)
                with connect() as con:
                    cur=con.execute('UPDATE locations SET general=?,clients=?,revision=revision+1 WHERE code=? AND revision=?',(general,clients,loc['code'],loc['revision']))
                    if not cur.rowcount:raise Problem('Draft berubah. Muat ulang lokasi.',409)
                audit('config',loc['code']+': '+('kebijakan diperbarui' if match[2]=='policy' else 'daftar peer diperbarui')+'.',actor)
                return self.response({'ok':True})
            match=re.fullmatch(r'/api/machines/([a-z0-9-]+)',path)
            if method=='PUT' and match:
                m=get_machine(match[1]);name=str(d.get('name','')).strip();user=str(d.get('ssh_user','')).strip()
                host=str(ipaddress.ip_address(d['host']));rid=str(ipaddress.IPv4Address(d['router_id']));port=int(d['ssh_port'])
                if not 2<=len(name)<=80 or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}',user) or not 1<=port<=65535:raise Problem('Data mesin tidak valid.')
                with MUTEX:
                    if query("SELECT 1 FROM jobs WHERE machine=? AND status='deploying'",(m['id'],),True):raise Problem('Mesin sedang deploy.',409)
                    with connect() as con:
                        params = [name,host,rid,user,port]
                        sql = "UPDATE machines SET name=?,host=?,router_id=?,ssh_user=?,ssh_port=?"
                        if 'ssh_key' in d:
                            sql += ",ssh_key=?"
                            params.append(d['ssh_key'])
                        sql += ",revision=revision+1,status='unverified',bird_version=NULL,checked_at=NULL WHERE id=? AND revision=?"
                        params.extend([m['id'],d.get('revision')])
                        cur=con.execute(sql, tuple(params))
                        if not cur.rowcount:raise Problem('Data mesin telah berubah. Muat ulang.',409)
                audit('machine',name+': pengaturan mesin diperbarui.',actor); sync_alice_now(); return self.response({'ok':True})
            match=re.fullmatch(r'/api/locations/([A-Z0-9-]+)',path)
            if method=='PUT' and match:
                loc=get_location(match[1]);general=d.get('general');clients=d.get('clients')
                if not isinstance(general,str) or not isinstance(clients,str):raise Problem('Dokumen YAML wajib berupa teks.')
                parsed(general,clients)
                validate_schema(general,clients)
                with connect() as c:
                    cur=c.execute('UPDATE locations SET general=?,clients=?,revision=revision+1 WHERE code=? AND revision=?',(general,clients,loc['code'],d.get('revision')))
                    if not cur.rowcount:raise Problem('Draft telah berubah di sesi lain. Muat ulang sebelum menyimpan.',409)
                audit('config','Draft '+loc['code']+' disimpan, revisi '+str(loc['revision']+1)+'.',actor);return self.response({'ok':True})
            match=re.fullmatch(r'/api/locations/([a-zA-Z0-9-]+)/templates/([^/]+)',path)
            if method=='PUT' and match:
                loc=get_location(match[1].upper());fname=match[2]
                if not re.fullmatch(r'^[a-zA-Z0-9_.-]+\.j2$',fname):raise Problem('Template tidak ditemukan.',404)
                content=d.get('content')
                if not isinstance(content,str):raise Problem('Konten template wajib berupa teks.')
                tdir=SOURCE/('arouteserver-'+loc['source'])/'templates'/'bird'
                tdir.mkdir(parents=True,exist_ok=True)
                tfile=tdir/fname
                tfile.write_text(content,encoding='utf-8')
                audit('config','Template '+fname+' di '+loc['code']+' diperbarui.',actor);return self.response({'ok':True})
            if method=='POST' and path=='/api/machines':
                loc=get_location(str(d.get('location','')))
                name=str(d.get('name','')).strip();user=str(d.get('ssh_user','root')).strip();host=str(d.get('host','')).strip()
                if not 2<=len(name)<=80 or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}',user):raise Problem('Nama mesin atau username SSH tidak valid.')
                ipaddress.ip_address(host);ipaddress.IPv4Address(d.get('router_id'))
                port=int(d.get('ssh_port',22))
                if not 1<=port<=65535:raise Problem('Port SSH tidak valid.')
                mid=secrets.token_hex(8)
                query('INSERT INTO machines(id,location,name,host,router_id,ssh_user,ssh_port,ssh_key) VALUES(?,?,?,?,?,?,?,?)',(mid,loc['code'],name,host,d['router_id'],user,port,d.get('ssh_key')))
                audit('machine',name+' ditambahkan ke '+loc['code']+'.',actor); sync_alice_now(); return self.response({'id':mid},201)
            match=re.fullmatch(r'/api/machines/([a-z0-9-]+)/(check|build)',path)
            if method=='POST' and match:
                m=get_machine(match[1])
                if match[2]=='check':return self.response(check_machine(m['id'],actor))
                loc=get_location(m['location']);jid=secrets.token_hex(16)
                with MUTEX:
                    if query("SELECT 1 FROM jobs WHERE machine=? AND status='generating'",(m['id'],),True):raise Problem('Build untuk mesin ini sedang berjalan.',409)
                    query('INSERT INTO jobs(id,machine,location,revision,machine_revision,status,created) VALUES(?,?,?,?,?,?,?)',(jid,m['id'],loc['code'],loc['revision'],m['revision'],'generating',time.time()))
                POOL.submit(generate_job,jid,loc,m,actor);return self.response({'id':jid},202)
            match=re.fullmatch(r'/api/machines/([a-z0-9-]+)/deployments/([0-9A-Fa-fTZ-]+)/rollback',path)
            if method=='POST' and match:return self.response(rollback_deployment(match[1],match[2],d.get('confirmation'),actor),202)
            match=re.fullmatch(r'/api/jobs/([a-f0-9]+)/(validate|deploy)',path)
            if method=='POST' and match:
                j=get_job(match[1])
                if match[2]=='deploy':return self.response(deploy_job(j['id'],d.get('confirmation'),actor),202)
                if not j['config']:raise Problem('Belum ada konfigurasi hasil build.',409)
                with MUTEX:
                    j=get_job(j['id'])
                    if j['status'] in ['generating','validating','deploying','deployed']:raise Problem('Build sedang diproses atau sudah diterapkan.',409)
                    update_job(j['id'],'validating','Menjalankan parser BIRD '+VERSION+'…')
                POOL.submit(validate_job,j['id'],actor);return self.response({'id':j['id']},202)
            raise Problem('Endpoint tidak ditemukan.',404)
        except Problem as e:self.response({'error':e.message},e.status)
        except sqlite3.IntegrityError:self.response({'error':'Kode atau data sudah terdaftar.'},409)
        except (ValueError,TypeError,KeyError) as e:self.response({'error':'Input tidak valid: '+str(e)},400)
        except Exception as e:
            print(type(e).__name__,str(e),flush=True);self.response({'error':'Terjadi kesalahan pada server. Periksa log layanan.'},500)
    def login(self,d,setup):
        name=str(d.get('name','')).strip();password=str(d.get('password',''))
        addr=self.client_address[0]
        with MUTEX:
            attempts=[t for t in LOGIN_ATTEMPTS.get(addr,[]) if t>time.time()-300]
            if len(attempts)>=10:raise Problem('Terlalu banyak percobaan. Coba lagi dalam 5 menit.',429)
            LOGIN_ATTEMPTS[addr]=attempts+[time.time()]
            u=query('SELECT * FROM users WHERE name=?',(name,),True)
            if setup:
                if query('SELECT 1 FROM users LIMIT 1',one=True):raise Problem('Administrator sudah dibuat.',409)
                expected=os.environ.get('MIMBAR_SETUP_TOKEN','')
                if not expected or not hmac.compare_digest(str(d.get('setup_token','')),expected):raise Problem('Token penyiapan tidak cocok. Lihat terminal layanan dashboard.',403)
                if not 2<=len(name)<=64 or len(password)<12 or len(password)>256:raise Problem('Gunakan nama 2–64 karakter dan password 12–256 karakter.')
                user_id=create_super_admin(name,password)
                u=query('SELECT * FROM users WHERE id=?',(user_id,),True)
                audit('account','Super-admin dibuat.',name)
            else:
                salt=u['salt'] if u else '0'*32
                digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),310000).hex()
                if not u or name!=u['name'] or not hmac.compare_digest(digest,u['password']):raise Problem('Nama pengguna atau password salah.',401)
            LOGIN_ATTEMPTS.pop(addr,None)
            token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
            query('DELETE FROM sessions WHERE expires<?',(time.time(),))
            query('INSERT INTO sessions(token,csrf,expires,user_id) VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),csrf,time.time()+28800,u['id']))
            return self.response({'user':name,'role':u['role'],'csrf':csrf},cookie=self.cookie(token,28800))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8787);parser.add_argument('--validator',choices=['disabled','docker'],default=os.environ.get('MIMBAR_VALIDATOR','disabled'));args=parser.parse_args()
    os.environ['MIMBAR_VALIDATOR']=args.validator
    os.umask(0o077);init();rrd_manager.start_background_collector()
    if not query('SELECT 1 FROM users',one=True):
        os.environ.setdefault('MIMBAR_SETUP_TOKEN',secrets.token_urlsafe(18))
        token_file=DATA/'setup-token'
        token_file.write_text(os.environ['MIMBAR_SETUP_TOKEN']);token_file.chmod(0o600)
        print('Token penyiapan admin tersimpan di '+str(token_file),flush=True)
    print(f'Mimbar dashboard: http://{args.host}:{args.port}',flush=True)
    ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()