"""Refuse streamed CSV exports (`?_stream=on`) on configured databases.

A streamed export walks the whole table page by page in one request, so
`sql_time_limit_ms` (per page) never stops it and `max_csv_mb` is the only
bound. On the Parquet-backed `usaspending` views that is hours of decode: on
2026-10-07 13:48Z and 2026-10-08 02:17Z a crawler on ASN 8075 requested
/usaspending/contracts.csv?_size=max&_stream=on, all 4 vCPUs pegged within
minutes, the CPU-credit bank drained in ~45 min, and the box sat throttled at
baseline (10-25s on every request) for hours. query_concurrency.py only gates
custom SQL, so it never saw these.

Cloudflare blocks the same requests at the edge (labordata_firewall
rules.yaml); this is the origin-side backstop. `allow_csv_stream` is a global
setting, and streams on the native tables are cheap and used (laborlab's nlrb
refresh), so this is per database. Non-streamed .csv/.json (one page) still
work.

The crawler got the URL from the "CSV" link on the table page, which
templates/table.html and query.html build with `&_stream=on`. Blocking alone
would leave a dead link, so this also sets `csv_stream_allowed` for those
templates; on configured databases the link downloads the current page instead.

    plugins:
      no-csv-stream:
        databases: [usaspending]
"""
from urllib.parse import parse_qs

from datasette import hookimpl

FORBIDDEN_BODY = (
    b"403: streaming full exports of this database is disabled (it overloads "
    b"the server). Filter the table and page through results with _next.\n"
)


def _databases(datasette):
    return (datasette.plugin_config("no-csv-stream") or {}).get("databases") or []


def _is_blocked(scope, databases):
    parts = [p for p in scope.get("path", "").split("/") if p]
    if not parts:
        return False
    # /<db>/... or /<db>.csv?sql=... (with or without the -<hash> suffix)
    db = parts[0].split(".")[0]
    if not any(db == name or db.startswith(name + "-") for name in databases):
        return False
    query = scope.get("query_string", b"").decode("latin-1")
    return "_stream" in parse_qs(query, keep_blank_values=True)


@hookimpl
def asgi_wrapper(datasette):
    def wrap(app):
        async def wrapped(scope, receive, send):
            if scope.get("type") == "http":
                if _is_blocked(scope, _databases(datasette)):
                    await send(
                        {
                            "type": "http.response.start",
                            "status": 403,
                            "headers": [
                                [b"content-type", b"text/plain; charset=utf-8"]
                            ],
                        }
                    )
                    await send(
                        {"type": "http.response.body", "body": FORBIDDEN_BODY}
                    )
                    return
            await app(scope, receive, send)

        return wrapped

    return wrap


@hookimpl
def extra_template_vars(database, datasette):
    return {
        "csv_stream_allowed": datasette.setting("allow_csv_stream")
        and database not in _databases(datasette)
    }
