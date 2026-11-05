#!/usr/bin/env bash
# Copies the site and rebuilds status.json from the ledger (run by publish.timer).
set -u
cd "$(dirname "$0")/.."
W=${VFS_WEBROOT:-/var/www/vaults}
mkdir -p "$W"
cp -r site/. "$W/"
python3 run.py publish "$W" > /dev/null
