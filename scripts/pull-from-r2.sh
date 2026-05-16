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
  python -c "import urllib.request,sys,os; urllib.request.urlretrieve(sys.argv[1], os.path.basename(sys.argv[1]))" \
    "$BASE/$name"
done

ls -la /data/incoming
