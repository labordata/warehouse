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

# Wait for uvicorn to be listening. Datasette's startup is bounded by
# how long it takes to mmap ~10 GB of .db files on a cold volume, which
# can be tens of seconds on shared-cpu-1x. Retry the cheapest endpoint
# every 2 s for up to 2 minutes before giving up.
deadline = time.time() + 120
while True:
    try:
        urllib.request.urlopen(BASE + "/-/versions.json", timeout=5).read()
        break
    except (urllib.error.URLError, ConnectionRefusedError) as e:
        if time.time() > deadline:
            print(f"datasette never became ready: {e}", file=sys.stderr)
            sys.exit(1)
        time.sleep(2)

# DIAGNOSTIC: read the shipped /data/internal.db directly (separate sqlite
# connection from datasette) to see whether the frozen catalog is being
# reused or re-populated. If catalog_databases has each db at schema_version
# 0 with a populated catalog_tables, reuse SHOULD skip live introspection.
try:
    import sqlite3
    ic = sqlite3.connect("file:/data/internal.db?mode=ro", uri=True)
    print("--- internal.db catalog_databases (name | schema_version | path) ---")
    for r in ic.execute("select database_name, schema_version, path from catalog_databases order by 1"):
        print(f"    {r[0]:>30} | sv={r[1]} | {r[2]}")
    print("--- internal.db catalog_tables counts ---")
    for r in ic.execute("select database_name, count(*) from catalog_tables group by 1 order by 1"):
        print(f"    {r[0]:>30} | {r[1]} tables")
    ic.close()
except Exception as e:
    print(f"    (could not read /data/internal.db: {e})")

versions_body, t = get("/-/versions.json")
print(f"/-/versions.json   {len(versions_body):>7} bytes  {t:>6.0f} ms")

databases_body, t = get("/-/databases.json")
print(f"/-/databases.json  {len(databases_body):>7} bytes  {t:>6.0f} ms")
dbs = json.loads(databases_body)
names = sorted(d["name"] for d in dbs)
print(f"  attached: {len(dbs)} databases: {names}")

expected = {
    "osha_enforcement", "nlrb", "opdr", "whisard", "lm10", "lm20", "lm30",
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

# Touch one real query per database so the smoke covers actual mmap, and
# assert the schema catalog (internal.db) actually lists tables for it. A db
# that attaches and answers queries but lists 0 tables is the cats failure
# mode (frozen/incomplete internal.db) — catch it at serve time too, not just
# in the offline build gate.
empty = []
for name in sorted(got):
    # 300s: a cold first render of the cats db landing page (282 tables) can
    # take minutes if datasette re-populates the catalog (282 per-table
    # column-detail queries on a cold 433 MB file). On staging there's no
    # public traffic to race, so let it finish rather than tail-fail.
    body, t = get(f"/{name}.json?_size=0", timeout=300)
    ntables = len(json.loads(body).get("tables", []))
    print(f"  /{name:>30}.json?_size=0   {t:>6.0f} ms  ({ntables} tables)")
    if ntables == 0:
        empty.append(name)
if empty:
    print(f"  EMPTY CATALOG (internal.db incomplete): {empty}", file=sys.stderr)
    sys.exit(1)
PY
