#!/bin/sh
# Pull data assets from the R2 staging bucket directly into /data.
#
# Used by the blue/green refresh path: each refresh spins up a fresh
# empty volume mounted at /data, this script populates it directly
# (no /data/incoming or swap-data.sh intermediation), and the machine
# is then restarted to mmap the new files. Compare with
# pull-from-r2.sh which stages into /data/incoming on a long-lived
# volume that has prior data still in /data.
#
# Usage: pull-from-r2-direct.sh <public-base> <name>...

set -eu

BASE="$1"
shift

cd /data

for name in "$@"; do
  echo "Pulling $BASE/$name"
  # See pull-from-r2.sh for why the explicit UA is necessary
  # (Cloudflare BIC rule 1010 on the bunkum.us zone). Same fix here.
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

ls -la /data
