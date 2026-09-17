#!/usr/bin/env python3
"""Install as root-owned /usr/local/sbin/mimbar-deploy on each RS.
Invoked through sudo by the dedicated SSH account. Accepts status/apply only.
No user-controlled shell commands, paths or BIRD includes are accepted.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import secrets
import subprocess
import sys
import time

CONFIG=Path('/etc/bird/bird.conf')
BIRD='/usr/sbin/bird'
BIRDC='/usr/sbin/birdc'
TARGET='2.19.2'
STATE=Path('/var/lib/mimbar')

def command(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=30)
    result=(p.stdout+'\n'+p.stderr).strip()
    if p.returncode:raise RuntimeError(result)
    if args[0]==BIRDC and re.search(r'^\s*[89]\d{3}',result,re.M):raise RuntimeError(result)
    return result

def birdc(*args):
    # birdc concatenates argv into its command language; filenames need quotes.
    encoded=['\"'+a+'\"' if a.startswith('/') else a for a in args]
    return command([BIRDC,'-v',*encoded])

def save_state(path,data):
    temp=path.with_suffix('.tmp')
    with temp.open('w') as out:
        json.dump(data,out);out.flush();os.fsync(out.fileno())
    os.replace(temp,path)

def watchdog(ident,lock_fd):
    # Detached child holds the inherited lock until commit or crash recovery.
    if os.geteuid()!=0 or not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[a-f0-9]{12}-[a-f0-9]{8}',ident):raise RuntimeError('Invalid watchdog transaction.')
    transaction=STATE/(ident+'.json')
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        state=json.loads(transaction.read_text())
        if state['state']!='pending':return
        time.sleep(.5)
    state=json.loads(transaction.read_text())
    if state['state']!='pending':return
    backup=STATE/(ident+'.backup.conf')
    restore=CONFIG.parent/('mimbar-recovery-'+ident+'.conf')
    try:
        shutil.copy2(backup,restore);os.chown(restore,state['uid'],state['gid']);os.replace(restore,CONFIG)
        result=birdc('configure',str(CONFIG))
        save_state(transaction,{'state':'rolled_back_after_timeout','output':result})
    except Exception as e:save_state(transaction,{'state':'rollback_failed','error':str(e)})
    finally:os.close(lock_fd)

def main():
    if len(sys.argv)==4 and sys.argv[1]=='watchdog':
        watchdog(sys.argv[2],int(sys.argv[3]));return
    if len(sys.argv)!=2 or sys.argv[1] not in ('status','apply'):raise RuntimeError('Usage: mimbar-deploy status|apply')
    version=command([BIRD,'--version'])
    if sys.argv[1]=='status':
        print(version);print(birdc('show','status'));return
    if os.geteuid()!=0:raise RuntimeError('Agent must run as root.')
    if not re.search(r'\b2\.19\.2\b',version):raise RuntimeError('Target must run BIRD 2.19.2.')
    raw=sys.stdin.buffer.read(2_000_001)
    if len(raw)>2_000_000:raise RuntimeError('Payload too large.')
    data=json.loads(raw);config=data['config']
    if not isinstance(config,str) or data.get('version')!=TARGET:raise RuntimeError('Invalid payload.')
    digest=hashlib.sha256(config.encode()).hexdigest()
    if digest!=data['sha256']:raise RuntimeError('Checksum mismatch.')
    # Require a self-contained artifact; do not let a config inspect arbitrary remote files.
    if re.search(r'\binclude\s',config,re.I):raise RuntimeError('Include directives are not allowed in deployment artifacts.')
    if not CONFIG.is_file() or CONFIG.is_symlink():raise RuntimeError('Expected a regular existing /etc/bird/bird.conf.')
    STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    lock=(STATE/'deploy.lock').open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    ident=time.strftime('%Y%m%d-%H%M%S')+'-'+digest[:12]+'-'+secrets.token_hex(4)
    backup=STATE/(ident+'.backup.conf')
    candidate=CONFIG.parent/('mimbar-'+ident+'.conf')
    candidate.write_text(config);candidate.chmod(0o640)
    oldstat=CONFIG.stat();os.chown(candidate,oldstat.st_uid,oldstat.st_gid)
    shutil.copystat(CONFIG,candidate)
    logs=[];activated=False
    try:
        logs.append(command([BIRD,'-p','-c',str(candidate)]))
        logs.append(birdc('configure','check',str(candidate)))
        shutil.copy2(CONFIG,backup)
        transaction=STATE/(ident+'.json')
        save_state(transaction,{'state':'pending','uid':oldstat.st_uid,'gid':oldstat.st_gid})
        subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'watchdog',ident,str(lock.fileno())],pass_fds=(lock.fileno(),),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        # Reconfigure from candidate first. On process death or SSH loss, BIRD reverts
        # to its old config after 90s. Active disk configuration is still unchanged.
        logs.append(birdc('configure',str(candidate),'timeout','90'));activated=True
        logs.append(birdc('show','status'))
        logs.append(birdc('show','protocols'))
        # Promote the same bytes, and return to the canonical filename while the
        # watchdog is still active. Back up file metadata and restore on any failure.
        os.replace(candidate,CONFIG)
        logs.append(birdc('configure',str(CONFIG),'timeout','90'))
        logs.append(birdc('show','status'))
        logs.append(birdc('configure','confirm'))
        save_state(transaction,{'state':'committed'})
        print(json.dumps({'status':'deployed','sha256':digest,'backup':str(backup),'output':logs}))
    except Exception as e:
        recovery=[]
        if backup.exists():
            restore=CONFIG.parent/('mimbar-restore-'+ident+'.conf')
            shutil.copy2(backup,restore);os.chown(restore,oldstat.st_uid,oldstat.st_gid);os.replace(restore,CONFIG)
            if activated:
                try:recovery.append(birdc('configure',str(CONFIG)))
                except Exception as rollback_error:recovery.append('ROLLBACK FAILED: '+str(rollback_error))
        if 'transaction' in locals():
            save_state(transaction,{'state':'failed','error':str(e),'recovery':recovery})
        raise RuntimeError(str(e)+'; recovery='+str(recovery))
    finally:
        candidate.unlink(missing_ok=True)

if __name__=='__main__':
    try:main()
    except Exception as e:
        print(json.dumps({'status':'failed','error':str(e)}),file=sys.stderr);sys.exit(1)
