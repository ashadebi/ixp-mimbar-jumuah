
import sqlite3, os, re
DASH=os.environ.get('DASHBOARD_DB','/dashboard-data/mimbar.sqlite3')
def norm(s): return re.sub(r'[^a-z0-9]','',(s or '').lower())
def correlate(parsed):
 out={'switch_ip':parsed.get('source_ip'),'parsed_interface':parsed.get('interface'),'mac':parsed.get('mac'),'admin_port':None,'snmp':None,'mismatch':None}
 if not os.path.exists(DASH): return out
 try:
  con=sqlite3.connect(DASH); con.row_factory=sqlite3.Row
  sw=con.execute('select id,name,ip from switches where ip=?',(parsed.get('source_ip'),)).fetchone()
  if sw:
   out['switch']={'id':sw['id'],'name':sw['name'],'ip':sw['ip']}
   iface=parsed.get('interface') or ''
   port=con.execute('select p.*,m.name member_name from ports p left join iixji_members m on m.asn=p.member_asn where p.switch_id=? and lower(p.port_number)=lower(?)',(sw['id'],iface)).fetchone()
   if not port and iface:
    rows=con.execute('select p.*,m.name member_name from ports p left join iixji_members m on m.asn=p.member_asn where p.switch_id=?',(sw['id'],)).fetchall()
    ni=norm(iface)
    for r in rows:
     if norm(r['port_number'])==ni: port=r; break
   if port: out['admin_port']={k:port[k] for k in port.keys() if k!='id'}
  con.close()
 except Exception as e: out['error']=str(e)[:120]
 out['mismatch']= bool(out.get('admin_port') and out.get('parsed_interface') and norm(out['admin_port'].get('port_number'))!=norm(out.get('parsed_interface')))
 return out
