import sqlite3
import os
import subprocess

DB_PATH = '/opt/arouterserver/dashboard/data/mimbar.sqlite3'
ALICE_CONF_PATH = '/opt/arouterserver/alice-lg/alice.conf'

def generate_conf():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, name, host FROM machines")
    machines = cur.fetchall()
    
    conf = ["[server]\nlisten_http = 0.0.0.0:8990\n\n[theme]\npath = /theme\nurl_base = /theme\n"]
    
    for m_id, m_name, m_host in machines:
        conf.append(f"[source.{m_id}]\nname = {m_name}\n")
        conf.append(f"[source.{m_id}.birdwatcher]\napi = http://{m_host}:29999/\ntype = multi_table\npeer_table_prefix = T\npipe_protocol_prefix = M\n")
    
    return "\n".join(conf)

def main():
    new_conf = generate_conf()
    try:
        with open(ALICE_CONF_PATH, 'r') as f:
            old_conf = f.read()
    except Exception:
        old_conf = ""
        
    if old_conf != new_conf:
        with open(ALICE_CONF_PATH, 'w') as f:
            f.write(new_conf)
        print("Updated alice.conf")
        subprocess.run(["docker", "restart", "alice-lg"], check=False)

if __name__ == "__main__":
    main()
