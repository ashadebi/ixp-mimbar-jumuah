import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_install_requires_explicit_deploy():
    p=subprocess.run(['sh',str(ROOT/'install.sh'),'--help'],capture_output=True,text=True)
    assert p.returncode==0
    assert '--deploy' in p.stdout and '--rollback' in p.stdout

def test_invalid_action_fails_before_side_effects():
    p=subprocess.run(['sh',str(ROOT/'install.sh'),'--not-an-action'],capture_output=True,text=True)
    assert p.returncode==2
