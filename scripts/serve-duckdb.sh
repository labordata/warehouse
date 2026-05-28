#!/bin/sh
# Serve the .duckdb databases on the mounted volume via the datasette-duckdb
# backend plugin.
#
# IMPORTANT: unlike the SQLite track (serve.sh), we must NOT pass the files
# with `-i`. `-i path` attaches a file with datasette's default SQLite backend,
# which then tries to read the .duckdb file as SQLite and crashes the process
# on startup ("file is not a database"). The DuckDB backend is mounted instead
# through plugin config: plugins.datasette-duckdb.databases = {name: path}.
# So we discover /data/*.duckdb at boot, merge them into a runtime copy of the
# static config, and serve that.
#
# If /data has no .duckdb files yet (first boot / pre-upload during a refresh
# cycle), the databases map is empty and datasette starts with no databases so
# the /-/versions.json health check still passes and the refresh can SFTP files
# in, then restart.

set -eu

DATA_DIR="${DATA_DIR:-/data}"
BASE_CONFIG=/app/datasette.duckdb.yml
RUNTIME_CONFIG=/tmp/datasette-runtime.yml

# Merge discovered *.duckdb files into the plugin's databases map. datasette
# depends on PyYAML, so it's importable here.
python3 - "$DATA_DIR" "$BASE_CONFIG" "$RUNTIME_CONFIG" <<'PY'
import glob, os, sys, yaml

data_dir, base_config, runtime_config = sys.argv[1], sys.argv[2], sys.argv[3]

with open(base_config) as f:
    cfg = yaml.safe_load(f) or {}

databases = {}
for path in sorted(glob.glob(os.path.join(data_dir, "*.duckdb"))):
    name = os.path.splitext(os.path.basename(path))[0]
    databases[name] = path

cfg.setdefault("plugins", {}).setdefault("datasette-duckdb", {})["databases"] = databases

with open(runtime_config, "w") as f:
    yaml.safe_dump(cfg, f, sort_keys=False)

print("serve-duckdb: mounting %d duckdb database(s): %s"
      % (len(databases), ", ".join(sorted(databases)) or "(none)"), file=sys.stderr)
PY

exec datasette serve \
  -c "$RUNTIME_CONFIG" \
  -m /app/warehouse_metadata.yml \
  -h 0.0.0.0 -p 8080 \
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
