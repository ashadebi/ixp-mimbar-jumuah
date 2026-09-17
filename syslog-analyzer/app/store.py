import sqlite3, time, os, json
DDL="""PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY,ts REAL NOT NULL,received REAL NOT NULL,source_ip TEXT,host TEXT,pri INTEGER,severity INTEGER,interface TEXT,mac TEXT,vendor TEXT,message TEXT,raw TEXT); CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts); CREATE INDEX IF NOT EXISTS idx_logs_src ON logs(source_ip,ts); CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,first_ts REAL,last_ts REAL,count INTEGER,type TEXT,severity INTEGER,confidence REAL,dedupe_key TEXT UNIQUE,log_id INTEGER,source_ip TEXT,host TEXT,interface TEXT,mac TEXT,vendor TEXT,message TEXT,correlation TEXT); CREATE INDEX IF NOT EXISTS idx_events_last ON events(last_ts); CREATE TABLE IF NOT EXISTS snmp_ports(switch_ip TEXT,if_index INTEGER,if_name TEXT,if_alias TEXT,if_descr TEXT,updated REAL,PRIMARY KEY(switch_ip,if_index));"""
class Store:
 def __init__(self,path,retention=129600):
  os.makedirs(os.path.dirname(path),exist_ok=True); self.path=path; self.retention=retention
  with self.conn() as c: c.executescript(DDL)
 def conn(self):
  c=sqlite3.connect(self.path,timeout=30); c.row_factory=sqlite3.Row; return c
 def add(self,p,events,correlate):
  with self.conn() as c:
   cur=c.execute('insert into logs(ts,received,source_ip,host,pri,severity,interface,mac,vendor,message,raw) values(?,?,?,?,?,?,?,?,?,?,?)',(p['ts'],time.time(),p.get('source_ip'),p.get('host'),p.get('pri'),p.get('severity'),p.get('interface'),p.get('mac'),p.get('vendor'),p.get('message'),p.get('raw'))); lid=cur.lastrowid
   for e in events:
    corr=correlate(p)
    row=c.execute('select id,count from events where dedupe_key=?',(e['dedupe_key'],)).fetchone()
    if row: c.execute('update events set last_ts=?,count=count+1,log_id=?,message=?,correlation=? where id=?',(p['ts'],lid,p.get('message'),json.dumps(corr),row['id']))
    else: c.execute('insert into events(first_ts,last_ts,count,type,severity,confidence,dedupe_key,log_id,source_ip,host,interface,mac,vendor,message,correlation) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(p['ts'],p['ts'],1,e['type'],e['severity'],e['confidence'],e['dedupe_key'],lid,p.get('source_ip'),p.get('host'),p.get('interface'),p.get('mac'),p.get('vendor'),p.get('message'),json.dumps(corr)))
  self.prune(); return lid
 def prune(self):
  cutoff=time.time()-self.retention
  with self.conn() as c:
   c.execute('delete from logs where ts<?',(cutoff,)); c.execute('delete from events where last_ts<?',(cutoff,));
  # lock-safe prune
  try:
   c=self.conn(); c.execute('pragma wal_checkpoint(truncate)'); c.close()
  except sqlite3.OperationalError: pass
 def list_logs(self,limit=100):
  with self.conn() as c: return [dict(r) for r in c.execute('select * from logs order by ts desc limit ?', (min(int(limit),500),))]
 def list_events(self,limit=100):
  with self.conn() as c: return [dict(r) for r in c.execute('select * from events order by last_ts desc limit ?', (min(int(limit),500),))]
 def summary(self):
  with self.conn() as c:
   return {'logs':c.execute('select count(*) n from logs').fetchone()['n'],'events':c.execute('select count(*) n from events').fetchone()['n'],'by_type':[dict(r) for r in c.execute('select type,count(*) events,sum(count) count from events group by type order by count desc')]} 
