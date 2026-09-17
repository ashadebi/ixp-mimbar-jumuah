#!/bin/sh
set -eu
cd "$(dirname "$0")"; docker compose -p mimbar-validation --env-file .env.example config >/dev/null; docker compose -p mimbar-validation build --no-cache
