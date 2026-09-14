"""Add view row counts to inspect-data.json.

Datasette uses inspect-data.json's count when it has one and otherwise runs a
count bounded at 10,001 -- which is what a view page shows, since a view has no
cheap count. The names under "tables" are looked up verbatim, so putting view
names there gives view pages a true row count.

    python scripts/inject_view_counts.py inspect-data.json usaspending usaspending-counts.json
"""
import json
import sys

inspect_file, database, counts_file = sys.argv[1:4]

with open(inspect_file) as f:
    inspect = json.load(f)
with open(counts_file) as f:
    counts = json.load(f)

entry = inspect.setdefault(database, {})
tables = entry.setdefault("tables", {})
for view, count in counts.items():
    tables.setdefault(view, {})["count"] = count

with open(inspect_file, "w") as f:
    json.dump(inspect, f)
print(f"injected {len(counts)} view count(s) into {inspect_file}: "
      + ", ".join(f"{v}={c:,}" for v, c in counts.items()))
