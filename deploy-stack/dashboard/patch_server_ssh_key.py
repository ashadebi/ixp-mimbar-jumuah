import re
import sys

with open('server.py', 'r') as f:
    src = f.read()

# 1. Add column in init()
src = src.replace("        if not c.execute('SELECT 1 FROM locations').fetchone():",
"""        try:
            c.execute('ALTER TABLE machines ADD COLUMN ssh_key TEXT')
        except sqlite3.OperationalError:
            pass
        if not c.execute('SELECT 1 FROM locations').fetchone():""")

# 2. Update summary() to mask ssh_key
src = src.replace("    return {'locations':locs,'machines':query('SELECT * FROM machines ORDER BY location DESC,name'),'jobs':query('SELECT id,machine,location,revision,machine_revision,status,created,log,sha256,validated_sha,validated_version FROM jobs ORDER BY created DESC LIMIT 30'),'events':query('SELECT * FROM events ORDER BY id DESC LIMIT 60'),'capabilities':capabilities()}",
"""    machines = query('SELECT * FROM machines ORDER BY location DESC,name')
    for m in machines: m['has_ssh_key'] = bool(m.pop('ssh_key', None))
    return {'locations':locs,'machines':machines,'jobs':query('SELECT id,machine,location,revision,machine_revision,status,created,log,sha256,validated_sha,validated_version FROM jobs ORDER BY created DESC LIMIT 30'),'events':query('SELECT * FROM events ORDER BY id DESC LIMIT 60'),'capabilities':capabilities()}""")

# 3. Update ssh_args(m)
new_ssh_args = """def ssh_args(m):
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
    return ['ssh','-F','/dev/null','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8','-o','UserKnownHostsFile='+hosts,'-i',key,'-p',str(m['ssh_port']),m['ssh_user']+'@'+m['host']]"""
src = re.sub(r"def ssh_args\(m\):.*?return \['ssh'.*?\]", new_ssh_args, src, flags=re.DOTALL)

# 4. Update PUT /api/machines
old_put = """                        cur=con.execute("UPDATE machines SET name=?,host=?,router_id=?,ssh_user=?,ssh_port=?,revision=revision+1,status='unverified',bird_version=NULL,checked_at=NULL WHERE id=? AND revision=?",(name,host,rid,user,port,m['id'],d.get('revision')))"""
new_put = """                        params = [name,host,rid,user,port]
                        sql = "UPDATE machines SET name=?,host=?,router_id=?,ssh_user=?,ssh_port=?"
                        if 'ssh_key' in d:
                            sql += ",ssh_key=?"
                            params.append(d['ssh_key'])
                        sql += ",revision=revision+1,status='unverified',bird_version=NULL,checked_at=NULL WHERE id=? AND revision=?"
                        params.extend([m['id'],d.get('revision')])
                        cur=con.execute(sql, tuple(params))"""
src = src.replace(old_put, new_put)

# 5. Update POST /api/machines
old_post = """                query('INSERT INTO machines(id,location,name,host,router_id,ssh_user,ssh_port) VALUES(?,?,?,?,?,?,?)',(mid,loc['code'],name,host,d['router_id'],user,port))"""
new_post = """                query('INSERT INTO machines(id,location,name,host,router_id,ssh_user,ssh_port,ssh_key) VALUES(?,?,?,?,?,?,?,?)',(mid,loc['code'],name,host,d['router_id'],user,port,d.get('ssh_key')))"""
src = src.replace(old_post, new_post)

with open('server.py', 'w') as f:
    f.write(src)
