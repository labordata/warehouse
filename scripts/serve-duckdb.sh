#!/bin/sh
# Discover .duckdb databases on the mounted volume and exec datasette with
# each one attached immutable (-i). Parallel to serve.sh, which does the same
# for SQLite .db files.
#
# Differences from serve.sh:
#   * globs *.duckdb (the converted files) instead of *.db
#   * no --crossdb: the SQLite track uses cross-database ATTACH for the
#     union_names canned queries, which are sqlite-specific; the DuckDB
#     backend serves one connection per database.
#   * no --inspect-file: `datasette inspect` is sqlite-shaped, so the DuckDB
#     refresh doesn't produce one. Datasette will scan on first request.
#
# If /data has no .duckdb files yet (first boot / pre-upload during a refresh
# cycle), start with no databases so the /-/versions.json health check still
# passes and the refresh can SFTP files in, then restart.

set -eu

DATA_DIR="${DATA_DIR:-/data}"

IMMUTABLE_ARGS=""
if ls "$DATA_DIR"/*.duckdb >/dev/null 2>&1; then
  for db in "$DATA_DIR"/*.duckdb; do
    IMMUTABLE_ARGS="$IMMUTABLE_ARGS -i $db"
  done
else
  echo "no .duckdb files in $DATA_DIR yet — starting datasette without any databases" >&2
fi

# shellcheck disable=SC2086  # args are intentionally word-split
exec datasette serve \
  $IMMUTABLE_ARGS \
  -h 0.0.0.0 -p 8080 \
  -c /app/datasette.duckdb.yml \
  -m /app/warehouse_metadata.yml \
  --plugins-dir /app/plugins \
  --template-dir /app/templates \
  --static static:/app/static \
  --cors \
  --setting sql_time_limit_ms 100000 \
  --setting facet_time_limit_ms 500 \
  --setting allow_facet off \
  --setting trace_debug 1 \
  --setting max_csv_mb 1000 \
  --setting force_https_urls on
