#!/bin/sh
# Pull data assets from the R2 staging bucket into /data/incoming.
#
# Usage:
#   pull-from-r2.sh <public-base> <name>...
#
# Each <name> becomes <public-base>/<name>, downloaded to
# /data/incoming/<basename>. urllib is used so we don't need to add curl
# to the slim image — single-stream Python downloads have measured at
# ~118 MB/s from this Fly machine to GitHub, which is faster than the
# Fly volume can write anyway.
#
# Wipes /data/incoming and /data/previous before pulling. /data/previous
# is unconditionally dropped because keeping it would push the 25 GB
# volume past its limit during the next swap (live + previous + incoming
# = ~30 GB peak). The rollback window we lose is just "before this
# deploy started"; if the deploy fails mid-way, re-run.

set -eu

BASE="$1"
shift

rm -rf /data/incoming /data/previous
mkdir /data/incoming
cd /data/incoming

for name in "$@"; do
  echo "Pulling $BASE/$name"
  # Set a real UA — Cloudflare's Browser Integrity Check on the
  # bunkum.us zone returns error 1010 to clients that look like
  # bots (Python-urllib/3.x by default), and the staging bucket
  # is on a custom domain inside that zone.
  python -c "
import urllib.request, sys, os
req = urllib.request.Request(sys.argv[1], headers={'User-Agent': 'warehouse-fly-pull/1.0'})
with urllib.request.urlopen(req) as r, open(os.path.basename(sys.argv[1]), 'wb') as f:
    while True:
        chunk = r.read(1 << 20)
        if not chunk: break
        f.write(chunk)
" "$BASE/$name"
done

ls -la /data/incoming
