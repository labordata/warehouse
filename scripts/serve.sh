#!/bin/sh
# Discover databases on the mounted volume and exec datasette with the same
# flags Cloud Run uses, plus -i for each .db (immutable mode).

set -eu

DATA_DIR="${DATA_DIR:-/data}"

if ! ls "$DATA_DIR"/*.db >/dev/null 2>&1; then
  echo "no .db files in $DATA_DIR; aborting" >&2
  exit 1
fi

IMMUTABLE_ARGS=""
for db in "$DATA_DIR"/*.db; do
  IMMUTABLE_ARGS="$IMMUTABLE_ARGS -i $db"
done

# shellcheck disable=SC2086  # $IMMUTABLE_ARGS is intentionally word-split
exec datasette serve \
  $IMMUTABLE_ARGS \
  -h 0.0.0.0 -p 8080 \
  -c /app/datasette.yml \
  -m /app/warehouse_metadata.yml \
  --plugins-dir /app/plugins \
  --crossdb \
  --cors \
  --setting sql_time_limit_ms 100000 \
  --setting facet_time_limit_ms 500 \
  --setting allow_facet off \
  --setting trace_debug 1 \
  --setting max_csv_mb 1000 \
  --setting force_https_urls on
