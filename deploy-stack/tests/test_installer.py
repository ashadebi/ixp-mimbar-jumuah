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


def test_installer_defaults_to_deploy_stack_project():
    text=(ROOT/'install.sh').read_text()
    assert 'PROJECT=${COMPOSE_PROJECT_NAME:-deploy-stack}' in text
    assert 'LEGACY_PROJECT=${LEGACY_COMPOSE_PROJECT_NAME:-mimbar-stack}' in text

def test_installer_writes_rrd_cron_fallback_and_removes_legacy_stats_container():
    text=(ROOT/'install.sh').read_text()
    assert 'CRON_FILE=${CRON_FILE:-/etc/cron.d/mimbar-rrd}' in text
    assert 'docker exec arouterserver-dashboard python3 -c' in text
    assert '$DOCKER_COMPOSE -p "$LEGACY_PROJECT" rm -sf stats-viewer' in text

def test_compose_uses_persistent_runtime_network_name():
    text=(ROOT/'docker-compose.yml').read_text()
    assert 'name: deploy-stack_mimbar-net' in text
