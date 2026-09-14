"""Build `usaspending.duckdb`: a database of VIEWS over the Parquet files that
labordata/usaspending publishes to R2.

The USAspending contract data is ~6.5 GB as Parquet and would be ~50 GB as
native DuckDB tables, so it is served as Parquet on the Fly volume rather than
converted. This script writes the database of views that points at it.

    python scripts/usaspending_views.py --data-dir /data --out usaspending.duckdb

`CREATE VIEW` resolves its Parquet paths immediately, so the files have to
exist when the view is made -- but the real ones are 6.5 GB and belong on the
Fly volume, not on a CI runner. So for each remote file this writes a *zero-row
placeholder* with the same schema (read over HTTP: footer and schema only) to
the path the view will reference. The refresh job then ships the real files to
those same paths on the volume, and the views resolve against real data with no
change to the stored SQL.

`--files-out` lists the paths the refresh job then pulls onto the volume,
relative to `--data-dir` -- prefix included, so that what lands on the volume
is exactly what the views reference. (The first promoted refresh pulled to
/data/contracts/... while the views looked in /data/usaspending/contracts/...
and every view page 500'd; the smoke test now queries each view to catch
that.)

Row counts come from the remote Parquet footers and are written to
`--counts-out`, for injecting into inspect-data.json: Datasette's bounded
count query reports ">10,000 rows" for a view otherwise, and inspect-data.json
is the one thing it will trust instead.
"""
import argparse
import json
import os
import re
import urllib.request

import duckdb

# Views to define: name -> the remote keys it unions, newest first for the
# per-year contract files so a bare `select *` starts in the current year.
VIEW_PATTERNS = {
    "contracts": re.compile(r"^contracts/FY(\d{4})\.parquet$"),
    "recipients": re.compile(r"^recipients\.parquet$"),
    "recipient_year": re.compile(r"^recipient_year\.parquet$"),
}


def list_keys(base):
    """Parquet keys published under the usaspending prefix.

    Enumerated from the fiscal years the API offers plus the two rollups,
    then confirmed with a HEAD -- the bucket has no public listing.
    """
    keys = ["recipients.parquet", "recipient_year.parquet"]
    keys += [f"contracts/FY{fy}.parquet" for fy in range(2008, 2100)]
    found = []
    misses = 0
    for key in keys:
        req = urllib.request.Request(f"{base}/{key}", method="HEAD",
                                     headers={"User-Agent": "warehouse-build/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30):
                found.append(key)
                misses = 0
        except urllib.error.HTTPError:
            misses += 1
            # fiscal years run out; stop after a couple of consecutive gaps
            if misses >= 3 and key.startswith("contracts/"):
                break
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://downloads.labordata.bunkum.us/usaspending")
    ap.add_argument("--data-dir", default="/data",
                    help="where the Parquet will live at serve time (placeholders go here too)")
    ap.add_argument("--out", default="usaspending.duckdb")
    ap.add_argument("--counts-out", default="usaspending-counts.json")
    ap.add_argument("--files-out", default="usaspending-files.json",
                    help="paths to pull onto the volume, relative to --data-dir "
                         "(so they include --prefix, matching what the views reference)")
    ap.add_argument("--prefix", default="usaspending")
    args = ap.parse_args()

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")

    keys = list_keys(args.base)
    print(f"{len(keys)} remote parquet file(s)")

    counts = {}
    local = {}
    for key in keys:
        url = f"{args.base}/{key}"
        path = os.path.join(args.data_dir, args.prefix, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            con.execute(f"COPY (SELECT * FROM '{url}' LIMIT 0) TO '{path}' (FORMAT parquet)")
        n = con.execute(f"SELECT sum(num_rows) FROM parquet_file_metadata('{url}')").fetchone()[0]
        local[key] = path
        counts[key] = int(n)
        print(f"  {key}: {n:,} rows")

    if os.path.exists(args.out):
        os.remove(args.out)
    db = duckdb.connect(args.out)
    view_counts = {}
    for view, pattern in VIEW_PATTERNS.items():
        members = sorted((k for k in keys if pattern.match(k)), reverse=True)
        if not members:
            continue
        paths = ", ".join(f"'{local[k]}'" for k in members)
        db.execute(f"CREATE VIEW {view} AS SELECT * FROM read_parquet([{paths}], union_by_name=true)")
        view_counts[view] = sum(counts[k] for k in members)
        print(f"view {view}: {len(members)} file(s), {view_counts[view]:,} rows")
    db.close()

    with open(args.counts_out, "w") as f:
        json.dump(view_counts, f, indent=2)
    with open(args.files_out, "w") as f:
        json.dump([f"{args.prefix}/{k}" for k in keys], f, indent=2)
    print(f"wrote {args.out} ({os.path.getsize(args.out):,} bytes), "
          f"{args.counts_out} and {args.files_out}")


if __name__ == "__main__":
    main()
