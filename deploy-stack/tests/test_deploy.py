import importlib, os, subprocess, sys, tempfile, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_analyzer_rejects_missing_and_predictable_token():
    code="import app.server"
    for value in (None, '', 'change-me', 'analyzer-secret-token'):
        env=os.environ.copy(); env['PYTHONPATH']=str(ROOT/'syslog-analyzer'); env['DATA_DIR']=tempfile.mkdtemp()
        if value is None: env.pop('SYSLOG_ANALYZER_TOKEN',None)
        else: env['SYSLOG_ANALYZER_TOKEN']=value
        p=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True)
        assert p.returncode != 0

def test_dashboard_rejects_missing_and_predictable_collector_token():
    code="import server"
    for value in (None, '', 'change-me', 'analyzer-secret-token'):
        env=os.environ.copy(); env['PYTHONPATH']=str(ROOT/'dashboard')
        if value is None: env.pop('SYSLOG_COLLECTOR_TOKEN',None)
        else: env['SYSLOG_COLLECTOR_TOKEN']=value
        p=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True)
        assert p.returncode != 0

def test_prune_once_removes_old_row_without_ingest(tmp_path):
    sys.path.insert(0,str(ROOT/'syslog-analyzer'))
    from app.store import Store
    db=tmp_path/'syslog.sqlite3'; store=Store(str(db),retention=10)
    with store.conn() as c:
        c.execute("insert into logs(ts,received,message,raw) values(?,?,?,?)",(time.time()-99,time.time()-99,'old','old'))
    env=os.environ.copy(); env.update(PYTHONPATH=str(ROOT/'syslog-analyzer'),DATA_DIR=str(tmp_path),RETENTION_SECONDS='10',SYSLOG_ANALYZER_TOKEN='unit-test-long-random-token')
    p=subprocess.run([sys.executable,'-m','app.pruner','--once'],env=env,capture_output=True,text=True)
    assert p.returncode == 0, p.stderr
    assert store.summary()['logs']==0
