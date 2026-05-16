#!/bin/sh
# Atomically swap in a newly uploaded set of .db files.
#
# Run on the Fly machine via `fly ssh console -C /app/scripts/swap-data.sh`
# after the upload step has placed files in /data/incoming/.
#
# Layout:
#   /data/current/         the live set datasette is serving (symlink target dir)
#   /data/incoming/        upload destination (build pipeline writes here)
#   /data/previous/        rolled-back set, kept for one cycle
#
# But for simplicity here, /data itself holds the live files. We move the
# incoming directory into place and let the supervisor restart datasette.

set -eu

DATA="${DATA_DIR:-/data}"
INCOMING="$DATA/incoming"

if [ ! -d "$INCOMING" ]; then
  echo "no $INCOMING directory; nothing to swap" >&2
  exit 1
fi

# Sanity: make sure every expected DB and the inspect file are present
EXPECTED="osha_enforcement nlrb opdr whisard lm10 lm20 chips cats f7 work_stoppages nlrb_rc_elections_1961_1998 voluntary_recognitions union_names_crosswalk"
for name in $EXPECTED; do
  if [ ! -f "$INCOMING/$name.db" ]; then
    echo "missing $INCOMING/$name.db; aborting swap" >&2
    exit 1
  fi
done
if [ ! -f "$INCOMING/inspect-data.json" ]; then
  echo "missing $INCOMING/inspect-data.json; aborting swap" >&2
  exit 1
fi

# Move old files out of the way, move new ones in. Datasette holds open
# file descriptors, so this is safe — the old files are unlinked from the
# namespace but stay accessible to the running process until restart.
mkdir -p "$DATA/previous"
rm -rf "$DATA/previous"/*.db "$DATA/previous"/inspect-data.json 2>/dev/null || true
mv "$DATA"/*.db "$DATA/previous"/ 2>/dev/null || true
mv "$DATA"/inspect-data.json "$DATA/previous"/ 2>/dev/null || true
mv "$INCOMING"/*.db "$DATA"/
mv "$INCOMING"/inspect-data.json "$DATA"/
rmdir "$INCOMING"

echo "swap complete; contents of $DATA:"
ls -la "$DATA"/*.db "$DATA"/inspect-data.json
