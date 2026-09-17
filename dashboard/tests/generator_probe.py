"""Render archive snapshots in scratch space; never certify them for deployment."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import yaml
ROOT=Path(__file__).resolve().parents[1]
results=[]
for site in ['ag','sub']:
    with tempfile.TemporaryDirectory(prefix='mimbar-generator-') as tmp:
        work=Path(tmp)
        src=ROOT.parent/('arouteserver-'+site)
        shutil.copytree(src,work/'input')
        p=work/'input';opts=yaml.safe_load((p/'arouteserver.yml').read_text()) or {}
        opts.update({'cfg_dir':str(p),'cache_expiry':10**10,'bgpq3_path':str(ROOT/'tools/bgpq4/usr/bin/bgpq4'),'bgpq3_timeout':3})
        (p/'arouteserver.yml').write_text(yaml.safe_dump(opts))
        cmd=[str(ROOT/'.venv/bin/arouteserver'),'bird','--cfg',str(p/'arouteserver.yml'),'--target-version','2.16','--logging-level','ERROR','-o',str(p/'bird.conf')]
        try:
            run=subprocess.run(cmd,capture_output=True,text=True,timeout=80)
            result={'location':site,'exit_code':run.returncode,'log':(run.stdout+run.stderr)[-6000:]}
            if run.returncode==0:
                result['config_bytes']=(p/'bird.conf').stat().st_size
                out=ROOT/'data/probes';out.mkdir(parents=True,exist_ok=True)
                shutil.copy2(p/'bird.conf',out/('snapshot-'+site+'.conf'))
                result['artifact']=str(out/('snapshot-'+site+'.conf'))
        except subprocess.TimeoutExpired:result={'location':site,'error':'Snapshot rendering exceeded 80 seconds.'}
        results.append(result)
out=ROOT/'data/probes';out.mkdir(parents=True,exist_ok=True)
(out/'generator-report.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
