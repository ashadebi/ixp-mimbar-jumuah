"""Runs exclusively inside the isolated lab container. No production addresses."""
import hashlib
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import time

config=Path('/etc/bird/bird.conf')
original='log stderr all;\nrouter id 192.0.2.1;\nprotocol device {}\n'
candidate=original+'protocol static sample { ipv4; route 198.51.100.0/24 blackhole; }\n'
config.write_text(original)
bird=subprocess.Popen(['/usr/sbin/bird','-f','-c',str(config)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
try:
    for _ in range(50):
        if Path('/run/bird.ctl').exists():break
        if bird.poll() is not None:raise RuntimeError(bird.stderr.read())
        time.sleep(.1)
    def payload(text):return json.dumps({'config':text,'sha256':hashlib.sha256(text.encode()).hexdigest(),'version':'2.19.2'})
    def apply(text):return subprocess.run(['/usr/local/sbin/mimbar-deploy','apply'],input=payload(text),capture_output=True,text=True,timeout=30)
    good=apply(candidate)
    assert good.returncode==0,(good.stdout,good.stderr)
    response=json.loads(good.stdout);assert response['status']=='deployed'
    assert config.read_text()==candidate
    assert Path(response['backup']).read_text()==original
    print('PASS: actual BIRD daemon, parser, backup, normal reload, confirmation and file promotion',flush=True)
    time.sleep(.6)  # Allow the committed watchdog to release its inherited lock.
    bad=apply('router id invalid;')
    assert bad.returncode!=0
    assert config.read_text()==candidate
    print('PASS: invalid configuration rejected; active file preserved',flush=True)
    # Trigger a controlled failure after the first live reconfiguration. The
    # agent must restore both disk and daemon to the previous configuration.
    loader=importlib.machinery.SourceFileLoader('agent','/usr/local/sbin/mimbar-deploy')
    spec=importlib.util.spec_from_loader(loader.name,loader)
    agent=importlib.util.module_from_spec(spec);loader.exec_module(agent)
    real=agent.command
    failed=[False]
    def fail_once(args):
        if args[:3]==[agent.BIRDC,'-v','configure'] and len(args)>3 and args[3].strip(chr(34))==str(config) and 'timeout' in args and not failed[0]:
            failed[0]=True;raise RuntimeError('simulated interruption after promotion')
        return real(args)
    agent.command=fail_once
    next_config=original+'protocol static changed { ipv4; route 203.0.113.0/24 blackhole; }\n'
    sys.argv=['/usr/local/sbin/mimbar-deploy','apply']
    sys.stdin=io.TextIOWrapper(io.BytesIO(payload(next_config).encode()))
    try:agent.main();raise AssertionError('Expected controlled failure')
    except RuntimeError as e:assert 'simulated interruption' in str(e),str(e)
    assert config.read_text()==candidate
    routes=subprocess.check_output(['/usr/sbin/birdc','show','route'],text=True)
    assert '198.51.100.0/24' in routes and '203.0.113.0/24' not in routes,routes
    print('PASS: failure after promotion restored original disk configuration and live routes',flush=True)
finally:
    bird.terminate();bird.wait(timeout=5)
