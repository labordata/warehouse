#!/bin/sh
# Patiently force datasette through its first /-/databases.json so the cold
# schema scan completes before any short-timeout client (smoke test, the first
# real visitor) hits the endpoint. The scan introspects every table across
# every attached database and is one-time-per-process; once it completes the
# catalog is cached and subsequent requests are instant.
#
# Two-phase wait:
#   1. Poll /-/versions.json until uvicorn is bound. The workflow's
#      Wait-for-SSH step only checks Fly's hallpass SSH daemon (independent
#      of datasette), so this script runs while datasette may still be
#      starting up over the freshly-attached databases.
#   2. Hit /-/databases.json once with a long timeout to drive the cold scan
#      to completion.
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
import urllib.request, urllib.error, sys, time

# Phase 1: wait for uvicorn to bind 8080. 1 vCPU + datasette starting up over
# 13 attached databases can take tens of seconds before it accepts connections.
ready_deadline = time.time() + 180
while time.time() < ready_deadline:
    try:
        urllib.request.urlopen(
            "http://localhost:8080/-/versions.json", timeout=5
        ).read()
        break
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError) as e:
        last = e
        time.sleep(2)
else:
    print("warmup: datasette never bound to :8080 after 180s (%r)" % last,
          file=sys.stderr)
    sys.exit(1)
print("warmup: uvicorn ready")

# Phase 2: drive the cold schema scan to completion.
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
