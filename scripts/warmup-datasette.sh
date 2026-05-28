#!/bin/sh
# Patiently force datasette through its first /-/databases.json so the cold
# schema scan completes before any short-timeout client (smoke test, the first
# real visitor) hits the endpoint. The scan introspects every table across
# every attached database and is one-time-per-process; once it completes the
# catalog is cached and subsequent requests are instant.
#
# Why this exists for the DuckDB track but not SQLite:
#   * The SQLite warehouse passes `--inspect-file inspect-data.json` to
#     datasette, which precomputes per-table counts/schema hashes and skips
#     the runtime scan entirely.
#   * `datasette inspect` is sqlite-shaped and we don't have a DuckDB
#     equivalent yet, so the runtime scan happens. Measured on a freshly
#     populated shared-cpu-1x machine over the real warehouse data (~4 GB
#     across 13 dbs), the cold scan takes ~245 s — well beyond the smoke
#     test's 30 s per-request timeout.

python3 - <<'PY'
import urllib.request, sys, time

t = time.time()
try:
    body = urllib.request.urlopen(
        "http://localhost:8080/-/databases.json", timeout=600
    ).read()
except Exception as e:
    print("warmup FAILED after %.1fs: %r" % (time.time() - t, e), file=sys.stderr)
    sys.exit(1)
print("warmup databases.json: %.1fs  %d bytes" % (time.time() - t, len(body)))
PY
