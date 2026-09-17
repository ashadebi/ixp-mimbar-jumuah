
import sqlite3
import os

DB = os.environ.get('MIMBAR_DATA', '/opt/arouterserver/dashboard/data') + '/mimbar.sqlite3'
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

# check if nodes table exists
res = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='nodes'").fetchone()
if not res:
    print("Migrating nodes and switches...")
    c.executescript('''
    BEGIN TRANSACTION;
    CREATE TABLE IF NOT EXISTS nodes(id INTEGER PRIMARY KEY,location TEXT NOT NULL REFERENCES locations(code),name TEXT NOT NULL,created REAL NOT NULL DEFAULT (strftime('%s','now')));
    CREATE TABLE switches_new(id INTEGER PRIMARY KEY,node_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,name TEXT NOT NULL,ip TEXT NOT NULL,community TEXT NOT NULL,vendor TEXT,model TEXT,sys_name TEXT,sys_descr TEXT,created REAL NOT NULL DEFAULT (strftime('%s','now')));
    ''')
    
    # Need to migrate data from switches to nodes + switches_new
    locations = c.execute("SELECT DISTINCT location FROM switches").fetchall()
    
    for loc in locations:
        loc_code = loc['location']
        c.execute("INSERT INTO nodes(location, name) VALUES(?, 'Default Node ' || ?)", (loc_code, loc_code))
        
    c.execute('''
    INSERT INTO switches_new(id, node_id, name, ip, community, vendor, model, sys_name, sys_descr, created)
    SELECT s.id, n.id, s.name, s.ip, s.community, s.vendor, s.model, s.sys_name, s.sys_descr, s.created 
    FROM switches s
    JOIN nodes n ON n.location = s.location
    ''')
    
    c.executescript('''
    DROP TABLE switches;
    ALTER TABLE switches_new RENAME TO switches;
    COMMIT;
    ''')
    print("Migration complete")
else:
    print("Migration already done")
