# Mimbar stack

Isolated installer. Sources remain `/opt/arouterserver/dashboard` and `/opt/arouterserver/syslog-analyzer`; existing production containers untouched.

## Validate/build
`cp .env.example .env; chmod 600 .env; ./install.sh` (generates 48-byte URL-safe tokens when `.env` absent). `./validate.sh` performs non-destructive config/build validation. Never print `.env`.

## Deploy after parent approval
`docker compose -p mimbar-stack up -d`; verify `docker compose -p mimbar-stack ps` and `curl http://127.0.0.1:8989`. Collector API has no published port; dashboard reaches `http://syslog-analyzer:5514` only. Syslog binds TCP/UDP 514; restrict firewall source IPs.

## Rollback
`docker compose -p mimbar-stack down` preserves named volumes. Backup with `docker run --rm -v mimbar-stack_analyzer-data:/data -v "$PWD":/backup alpine tar czf /backup/analyzer-data.tgz -C /data .`. Restore prior reviewed image/config, then `up -d`. Do not delete volumes unless approved.

## WAF/firewall
Point WAF upstream to `http://127.0.0.1:8989`; keep `DASHBOARD_BIND_HOST=127.0.0.1`. Set `SYSLOG_BIND_HOST=0.0.0.0` only with host firewall allowlist, e.g. `iptables -A INPUT -p udp --dport 514 -s ALLOWED_IP -j ACCEPT` and equivalent TCP, then deny other 514; apply only after review. Do not expose 8989 publicly.

## Retention
Analyzer retention is 36h (`129600` seconds). Existing analyzer prunes on ingest. `analyzer-pruner` is scheduled loop intended to call prune every 36h; current source must expose `PRUNE_ONLY`/prune entrypoint before production deploy. Test against copy: insert old row, invoke approved prune entrypoint, confirm row count drops without ingest. Current source inspection found no such entrypoint, so this is a required parent-reviewed source change.
