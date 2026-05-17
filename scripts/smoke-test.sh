#!/bin/sh
# Smoke-test a freshly populated datasette container.
#
# Run via `flyctl ssh console -C` against a staging machine. Hits
# localhost:8080 endpoints and reports timings + database count.
# Exits non-zero if anything looks off so the workflow step fails
# loudly.

set -eu

python3 - <<'PY'
import json, sys, time, urllib.request

BASE = "http://localhost:8080"

def get(path, timeout=30):
    s = time.time()
    body = urllib.request.urlopen(BASE + path, timeout=timeout).read()
    return body, (time.time() - s) * 1000

versions_body, t = get("/-/versions.json")
print(f"/-/versions.json   {len(versions_body):>7} bytes  {t:>6.0f} ms")

databases_body, t = get("/-/databases.json")
print(f"/-/databases.json  {len(databases_body):>7} bytes  {t:>6.0f} ms")
dbs = json.loads(databases_body)
names = sorted(d["name"] for d in dbs)
print(f"  attached: {len(dbs)} databases: {names}")

expected = {
    "osha_enforcement", "nlrb", "opdr", "whisard", "lm10", "lm20",
    "chips", "cats", "f7", "work_stoppages",
    "nlrb_rc_elections_1961_1998", "voluntary_recognitions",
    "union_names_crosswalk",
}
got = set(names) - {"_memory"}
missing = expected - got
extra = got - expected
if missing:
    print(f"  MISSING: {sorted(missing)}", file=sys.stderr)
if extra:
    print(f"  EXTRA:   {sorted(extra)}")
if missing:
    sys.exit(1)

# Touch one real query per database so the smoke covers actual mmap.
for name in sorted(got):
    body, t = get(f"/{name}.json?_size=0", timeout=60)
    print(f"  /{name:>30}.json?_size=0   {t:>6.0f} ms")
PY
