#!/bin/sh
set -eu
usage(){ cat <<'EOF'
Usage: ./install.sh [--check|--build|--deploy|--rollback|--health]
  --check     generate .env if missing; run preflight and docker compose config
  --build     check then build images; no deploy
  --deploy    check, backup metadata, build, up -d, wait health
  --rollback  restore previous compose/image metadata when available; up -d
  --health    wait for current project health
Default: --build. No container changes unless --deploy or --rollback.
EOF
}
ACTION=--build
[ $# -eq 0 ] || ACTION=$1
case "$ACTION" in --help|-h) usage; exit 0;; --check|--build|--deploy|--rollback|--health) ;; *) usage >&2; exit 2;; esac
cd "$(dirname "$0")"
umask 077
PROJECT=${COMPOSE_PROJECT_NAME:-mimbar-stack}
RELEASE_DIR=${RELEASE_DIR:-releases}
mkdir -p "$RELEASE_DIR"
mkdir -p /opt/arouterserver/syslog-analyzer/data
chown -R 10000:10000 /opt/arouterserver/syslog-analyzer/data
need(){ command -v "$1" >/dev/null 2>&1 || { printf '%s\n' "missing dependency: $1" >&2; exit 1; }; }
secret(){ python3 -c 'import secrets; print(secrets.token_urlsafe(48))'; }
ensure_env(){
 if [ ! -f .env ]; then
  { printf 'DASHBOARD_BIND_HOST=0.0.0.0\n'; printf 'DASHBOARD_PORT=8989\n'; printf 'SYSLOG_BIND_HOST=0.0.0.0\n'; printf 'SYSLOG_PORT=514\n'; printf 'RETENTION_SECONDS=129600\n'; printf 'PRUNE_INTERVAL=300\n'; printf 'NETWORK_INTERNAL=false\n'; printf 'RELEASE_TAG=local\n'; printf 'SYSLOG_ANALYZER_TOKEN=%s\n' "$(secret)"; printf 'MIMBAR_SETUP_TOKEN=%s\n' "$(secret)"; } > .env
  chmod 600 .env
 else
  chmod 600 .env
 fi
}
load_env(){ set -a; . ./.env; set +a; }
strong(){ v=$1; [ ${#v} -ge 24 ] && [ "$v" != change-me ] && [ "$v" != analyzer-secret-token ] && [ "$v" != GENERATED_BY_install.sh ]; }
preflight(){
 need docker; need python3
DOCKER_COMPOSE="docker compose"
docker compose version >/dev/null 2>&1 || { docker-compose version >/dev/null 2>&1 && DOCKER_COMPOSE="docker-compose" || DOCKER_COMPOSE="docker compose"; }
 [ -f Dockerfile.dashboard ] && [ -f Dockerfile.analyzer ] && [ -d dashboard ] && [ -d syslog-analyzer ] || { printf '%s\n' 'missing build contexts' >&2; exit 1; }
 load_env
 strong "${SYSLOG_ANALYZER_TOKEN:-}" || { printf '%s\n' 'weak SYSLOG_ANALYZER_TOKEN' >&2; exit 1; }
 strong "${MIMBAR_SETUP_TOKEN:-}" || { printf '%s\n' 'weak MIMBAR_SETUP_TOKEN' >&2; exit 1; }
 for p in "${DASHBOARD_PORT:-8989}" "${SYSLOG_PORT:-514}"; do case $p in ''|*[!0-9]*) printf '%s\n' "invalid port: $p" >&2; exit 1;; esac; done
 $DOCKER_COMPOSE -p "$PROJECT" config >/dev/null
}
backup_meta(){
 TS=$(date -u +%Y%m%dT%H%M%SZ); D="$RELEASE_DIR/$TS"; mkdir -p "$D"
 cp docker-compose.yml "$D/docker-compose.yml"; cp .env "$D/env.backup"; chmod 600 "$D/env.backup"
 $DOCKER_COMPOSE -p "$PROJECT" ps --format json > "$D/ps.json" 2>/dev/null || true
 docker image inspect "mimbar-dashboard:${RELEASE_TAG:-local}" > "$D/dashboard-image.json" 2>/dev/null || true
 docker image inspect "mimbar-analyzer:${RELEASE_TAG:-local}" > "$D/analyzer-image.json" 2>/dev/null || true
 printf '%s\n' "$D" > "$RELEASE_DIR/last"
}
 health(){
 end=$(( $(date +%s) + 120 ))
 while [ $(date +%s) -lt $end ]; do
  st=$($DOCKER_COMPOSE -p "$PROJECT" ps 2>/dev/null || true)
  printf '%s\n' "$st" | grep -q 'syslog-analyzer' && printf '%s\n' "$st" | grep -q 'dashboard' && printf '%s\n' "$st" | grep -q 'alice-lg' && return 0
  sleep 2
 done
 $DOCKER_COMPOSE -p "$PROJECT" ps; exit 1
}
rollback(){
 [ -f "$RELEASE_DIR/last" ] || { printf '%s\n' 'no rollback metadata' >&2; exit 1; }
 D=$(cat "$RELEASE_DIR/last"); [ -f "$D/docker-compose.yml" ] && [ -f "$D/env.backup" ] || { printf '%s\n' 'rollback metadata incomplete' >&2; exit 1; }
 cp "$D/docker-compose.yml" docker-compose.yml; cp "$D/env.backup" .env; chmod 600 .env
 $DOCKER_COMPOSE -p "$PROJECT" up -d; health
}
ensure_env
case "$ACTION" in
 --check) preflight; printf '%s\n' 'check ok';;
 --build) preflight; $DOCKER_COMPOSE -p "$PROJECT" build; printf '%s\n' 'build ok; no deploy';;
 --deploy) preflight; backup_meta; $DOCKER_COMPOSE -p "$PROJECT" build; $DOCKER_COMPOSE -p "$PROJECT" up -d; health; printf '%s\n' 'deploy ok';;
 --rollback) rollback; printf '%s\n' 'rollback ok';;
 --health) load_env; health; printf '%s\n' 'health ok';;
esac
