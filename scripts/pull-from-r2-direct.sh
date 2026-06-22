#!/bin/sh
# Pull data assets from the R2 staging bucket directly into /data.
#
# Used by the blue/green refresh path: each refresh spins up a fresh
# empty volume mounted at /data, this script populates it directly,
# and the machine is then restarted to mmap the new files.
#
# wget rather than urllib: it verifies received bytes against
# Content-Length and retries (resuming) on truncated transfers. The
# previous hand-rolled urllib loop treated a dropped connection as
# end-of-file and wrote silently truncated files — datasette then
# crash-looped on "database disk image is malformed" at the smoke-test
# step (runs 26946671479, 27089444562, 27343324109).
#
# The explicit UA is necessary because Cloudflare BIC rule 1010 on the
# bunkum.us zone blocks requests with non-browser default user agents.
#
# Usage: pull-from-r2-direct.sh <public-base> <name>...

set -eu

BASE="$1"
shift

cd /data

for name in "$@"; do
  echo "Pulling $BASE/$name"
  # -O "$name" forces the output path and OVERWRITES. Without it, wget's
  # default is to write "$name.1" when "$name" already exists — which it does
  # for internal.db: the staging machine boots datasette against the fresh
  # volume before this pull runs, and datasette auto-creates an empty
  # /data/internal.db. The shipped catalog then landed as internal.db.1 and was
  # never read, so every db listed 0 tables (run 27922292539). -O also keeps
  # one canonical file across retries instead of accumulating .1/.2 suffixes.
  wget --user-agent="warehouse-fly-pull/1.0" \
       --tries=5 \
       --no-verbose \
       -O "$name" \
       "$BASE/$name"
done

ls -la /data
