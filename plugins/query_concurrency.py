"""Shed custom-SQL load when the shared DuckDB instance is saturated.

labordata runs on one shared-cpu-1x vCPU with a single shared DuckDB instance
(threads=1), so heavy custom-SQL queries serialize through one master
connection. With no limit, a single automated client firing expensive ad-hoc
joins makes every request queue behind it — including cheap pages like /cats —
until they blow past Cloudflare's ~100s origin timeout and 524. (2026-06-22:
a `research/1.0` agent doing OSHA analysis took the whole site down this way.)

This gates ONLY machine-format custom-SQL execution — a non-empty `sql=` param
on a `.json`/`.csv` path — with a global in-flight cap: once `max_concurrent`
are running, further ones get an immediate `429 + Retry-After` instead of
forming an unbounded queue. Everything else is untouched, so the box stays
responsive: table pages, /cats, static, /-/versions, and crucially the HTML
query pages (`/db/-/query?sql=`) — those are humans writing SQL interactively,
who run one query at a time and should never be 429'd mid-edit. The flood this
sheds is programmatic (the 2026-06-22 agent was ~entirely `.json`).

A concurrency cap (not a req/min rate) is self-tuning to actual load: the slot
is held for the FULL request, so cheap queries release it in milliseconds
(high throughput, nobody shed) while expensive ones hold it (the next heavy
query is shed precisely because the box is busy). No loadavg polling needed.

Why global, not per-client: the resource is singular (one vCPU / one master),
so the global count IS the resource model; per-client fairness is a separate
concern better handled at the edge (it sees IP/UA/bot-score; rotation across
IPs defeats per-client here anyway). Single uvicorn worker => a module-global
counter is authoritative.

The 429 is rendered through datasette's own error machinery — Response.json
for .json clients, otherwise the site-styled error.html (so it picks up
extra_css_urls etc.) — matching what datasette.handle_exception does. Drop a
`429.html` template in the template dir to customise it (e.g. add an
auto-refresh); datasette prefers `<status>.html` over `error.html`.

Config (datasette.yml):

    plugins:
      query-concurrency:
        max_concurrent: 3      # default 3 (= num_sql_threads ceiling)
        retry_after: 5         # seconds, advertised in the Retry-After header

`max_concurrent` above num_sql_threads (default 3) has no effect — a query that
can't get a worker thread waits regardless. Set 2 to always reserve a thread
for browsing; raise num_sql_threads first to go higher.
"""

from urllib.parse import parse_qs

from datasette import hookimpl
from datasette.utils.asgi import Request, Response

# Process-global in-flight count of custom-SQL requests. The asgi wrapper runs
# on the single event loop, so the check-then-increment below is atomic (no
# await between), and one uvicorn worker means this is the whole truth.
_inflight = 0

_DEFAULT_MAX = 3
_DEFAULT_RETRY_AFTER = 5

_MESSAGE = (
    "The database is busy running the maximum number of simultaneous queries. "
    "Please retry in a few seconds — and if you are querying programmatically, "
    "pace your requests and honour the Retry-After header."
)


def _is_gated(scope):
    """True for machine-format custom-SQL execution: a non-empty ``sql=`` param
    on a ``.json``/``.csv`` path.

    HTML query pages (``/db/-/query?sql=`` with no data extension) are
    deliberately NOT gated — those are humans writing SQL interactively in the
    browser, and a person should never get a 429 mid-edit. They run one query
    at a time anyway. The flood we're shedding is programmatic (the 2026-06-22
    agent was ~entirely ``.json``), so scoping to .json/.csv targets exactly
    the automated path and leaves the human-facing UI alone.
    """
    path = scope.get("path", "")
    if not (path.endswith(".json") or path.endswith(".csv")):
        return False
    qs = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    return any(v.strip() for v in qs.get("sql", []))


async def _send_busy(datasette, scope, receive, send, retry_after):
    info = {
        "ok": False,
        "error": _MESSAGE,
        "status": 429,
        "title": "Database busy",
    }
    # Never let a transient busy response be cached: a cached 429 would serve
    # "busy" to everyone even when the box is idle. Set both Cache-Control and
    # CDN-Cache-Control (Cloudflare prefers the latter when present) to no-store.
    # cdn_cache.py only tags 2xx, so it won't re-add a long TTL here.
    headers = {
        "retry-after": str(retry_after),
        "cache-control": "no-store",
        "cdn-cache-control": "no-store",
    }
    path = scope.get("path", "")
    if path.endswith(".json"):
        response = Response.json(info, status=429, headers=headers)
    elif path.endswith(".csv"):
        response = Response.text(
            "429 Too Many Requests\n\n" + _MESSAGE + "\n", status=429, headers=headers
        )
    else:
        # Mirror datasette.handle_exception: prefer <status>.html, fall back to
        # error.html, rendered via datasette so the page is styled like the site.
        html = await datasette.render_template(
            ["429.html", "error.html"], info, request=Request(scope, receive)
        )
        response = Response.html(html, status=429, headers=headers)
    await response.asgi_send(send)


@hookimpl
def asgi_wrapper(datasette):
    config = datasette.plugin_config("query-concurrency") or {}
    max_concurrent = int(config.get("max_concurrent", _DEFAULT_MAX))
    retry_after = int(config.get("retry_after", _DEFAULT_RETRY_AFTER))

    def wrap(app):
        async def inner(scope, receive, send):
            # Only gate real HTTP custom-SQL executions; everything else
            # (table/db pages, static, /-/versions, lifespan, websockets) flows
            # straight through and is never shed.
            if scope.get("type") != "http" or not _is_gated(scope):
                await app(scope, receive, send)
                return

            global _inflight
            if _inflight >= max_concurrent:
                await _send_busy(datasette, scope, receive, send, retry_after)
                return

            _inflight += 1
            try:
                await app(scope, receive, send)
            finally:
                _inflight -= 1

        return inner

    return wrap
