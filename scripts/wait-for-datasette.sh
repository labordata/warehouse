#!/bin/sh
# Poll /-/versions.json until uvicorn is bound (or fail after ~5 min).
#
# Wait-for-SSH on the workflow side only checks Fly's hallpass daemon,
# which is up in seconds — independent of datasette. On shared-cpu-1x with
# 13 .duckdb databases attached, datasette's own startup (plugin discovery
# + plugin startup hooks adding databases + check_databases per db) takes
# ~2 minutes, well past smoke-test.sh's built-in 120s poll. Use this BEFORE
# smoke, after promote port-update, and after deploy roll, so each of those
# steps runs against a datasette that has actually bound :8080.

python3 - <<'PY'
import urllib.request, urllib.error, sys, time

deadline = time.time() + 300  # ~5 min, well clear of observed ~2 min boots
last = None
while time.time() < deadline:
    try:
        urllib.request.urlopen(
            "http://localhost:8080/-/versions.json", timeout=5
        ).read()
        elapsed = 300 - (deadline - time.time())
        print("datasette ready after %.0fs" % elapsed)
        sys.exit(0)
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError) as e:
        last = e
        time.sleep(2)
print("datasette never bound :8080 after 300s (%r)" % last, file=sys.stderr)
sys.exit(1)
PY
