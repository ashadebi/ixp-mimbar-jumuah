"""Cross-check the real dashboard validator using BIRD 2.19.2 and archived snapshots."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('mimbar',ROOT/'server.py');app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
results=[]
with tempfile.TemporaryDirectory(prefix='mimbar-validator-') as tmp:
    app.DATA=Path(tmp);app.DB=app.DATA/'validator.sqlite3';app.init()
    os.environ['MIMBAR_VALIDATOR']='docker'
    inputs=[('smoke',(ROOT/'container/smoke.conf').read_text(),True),('ag',(ROOT/'data/probes/snapshot-ag.conf').read_text(),True),('sub',(ROOT/'data/probes/snapshot-sub.conf').read_text(),True),('invalid','router id not_an_ip;',False)]
    for idx,(name,config,expected) in enumerate(inputs):
        jid=f'{idx:032x}';digest=hashlib.sha256(config.encode()).hexdigest()
        app.query('INSERT INTO jobs(id,machine,location,revision,machine_revision,status,created,config,sha256) VALUES(?,?,?,?,?,?,?,?,?)',(jid,'sub-rs3','SUB',1,1,'generated',0,config,digest))
        app.validate_job(jid,'validator-test');j=app.get_job(jid)
        result={'case':name,'status':j['status'],'log':j['log'],'sha256':digest,'expected_valid':expected}
        results.append(result);print(json.dumps(result),flush=True)
        if (j['status']=='validated')!=expected:raise AssertionError(result)
(ROOT/'data/probes/validator-report.json').write_text(json.dumps(results,indent=2))
