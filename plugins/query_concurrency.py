"""Shed custom-SQL load when the shared DuckDB instance is saturated.

labordata runs on one shared-cpu-1x vCPU with a single shared DuckDB instance
(threads=1), so heavy custom-SQL queries serialize through one master
connection. With no limit, a single automated client firing expensive ad-hoc
joins makes every request queue behind it — including cheap pages like /cats —
until they blow past Cloudflare's ~100s origin timeout and 524. (2026-06-22:
a `research/1.0` agent doing OSHA analysis took the whole site down this way.)

This gates ONLY machine-format custom-SQL execution — a non-empty `sql=` param
on a `.json`/`.csv` path. Everything else is untouched, so the box stays
responsive: table pages, /cats, static, /-/versions, and crucially the HTML
query pages (`/db/-/query?sql=`) — those are humans writing SQL interactively
and must never be 429'd mid-edit. The flood this sheds is programmatic.

## Bounded-wait queue (not a hard reject)

A flat "N concurrent, else 429" cap can't tell a page firing 6 *cheap* cross-
origin queries (each ~50ms) from one client firing 6 *heavy* joins — it counts
both on arrival and 429s the excess, breaking legit multi-query pages (e.g. the
charts on notes.labordata.bunkum.us, which fan out ~6 concurrent `?sql=`
fetches).

So instead of rejecting on arrival, a request that finds all slots full WAITS
up to `queue_wait` seconds for one to free before giving up with a 429. Because
the slot is held for the whole request, the hold time IS the cost signal:

  - cheap burst (box idle): N run in ~50ms, the rest wait ~50ms, slots free,
    they run — all 200, page renders. The wait drains.
  - heavy flood: N run for seconds, the rest wait `queue_wait` and the slots
    DON'T free → 429. Still shed.

`max_queue` bounds how many may wait, so a flood can't pile up unbounded held
connections (beyond it → immediate 429). Honest limit: if the box is ALREADY
pegged by a heavy flood, a cheap query arriving then still waits and 429s — you
can't guarantee a cheap query on a genuinely-saturated 1-vCPU box. The common
case (page loads against an idle/cheap-loaded box) is fully handled.

Why global, not per-client: the resource is singular (one vCPU / one master),
so the global count IS the resource model; per-client fairness belongs at the
edge (IP/UA/bot-score; IP rotation defeats per-client here anyway). Single
uvicorn worker => module-global state is authoritative.

The 429 is rendered through datasette's own Response — JSON for .json, text for
.csv — with Cache-Control AND CDN-Cache-Control: no-store so Cloudflare never
caches a transient busy response (its labordata cache rule is bypass_by_default,
which honors no-store).

Config (datasette.yml):

    plugins:
      query-concurrency:
        max_concurrent: 3      # running slots (== num_sql_threads ceiling)
        queue_wait: 1.5        # seconds a full request waits for a slot
        max_queue: 20          # max waiters before immediate 429
        retry_after: 5         # advertised in the Retry-After header

`max_concurrent` above num_sql_threads (default 3) has no effect — a query that
can't get a worker thread waits regardless. Set 2 to always reserve a thread
for browsing; raise num_sql_threads first to go higher.
"""

import asyncio
from urllib.parse import parse_qs

from datasette import hookimpl
from datasette.utils.asgi import Response

# Module-global limiter state. The asgi wrapper runs on the single uvicorn event
# loop, so this is authoritative and needs no cross-process coordination. The
# Semaphore is created lazily on first use (inside a running loop).
_sem = None
_waiters = 0

_DEFAULT_MAX = 3
_DEFAULT_QUEUE_WAIT = 1.5
_DEFAULT_MAX_QUEUE = 20
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
    browser, and a person should never be 429'd mid-edit.
    """
    path = scope.get("path", "")
    if not (path.endswith(".json") or path.endswith(".csv")):
        return False
    qs = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    return any(v.strip() for v in qs.get("sql", []))


async def _send_busy(scope, send, retry_after):
    # Never let a transient busy response be cached: a cached 429 would serve
    # "busy" to everyone even when the box is idle. Set both Cache-Control and
    # CDN-Cache-Control (Cloudflare prefers the latter when present) to no-store.
    headers = {
        "retry-after": str(retry_after),
        "cache-control": "no-store",
        "cdn-cache-control": "no-store",
    }
    if scope.get("path", "").endswith(".csv"):
        response = Response.text(
            "429 Too Many Requests\n\n" + _MESSAGE + "\n", status=429, headers=headers
        )
    else:
        response = Response.json(
            {"ok": False, "status": 429, "error": _MESSAGE},
            status=429,
            headers=headers,
        )
    await response.asgi_send(send)


@hookimpl
def asgi_wrapper(datasette):
    config = datasette.plugin_config("query-concurrency") or {}
    max_concurrent = int(config.get("max_concurrent", _DEFAULT_MAX))
    queue_wait = float(config.get("queue_wait", _DEFAULT_QUEUE_WAIT))
    max_queue = int(config.get("max_queue", _DEFAULT_MAX_QUEUE))
    retry_after = int(config.get("retry_after", _DEFAULT_RETRY_AFTER))

    def wrap(app):
        async def inner(scope, receive, send):
            # Only gate real HTTP custom-SQL executions; everything else
            # (table/db pages, static, /-/versions, HTML query pages, lifespan,
            # websockets) flows straight through and is never shed.
            if scope.get("type") != "http" or not _is_gated(scope):
                await app(scope, receive, send)
                return

            global _sem, _waiters
            if _sem is None:
                _sem = asyncio.Semaphore(max_concurrent)

            # All slots full and the wait queue is also full: shed now rather
            # than hold yet another connection open.
            if _sem.locked() and _waiters >= max_queue:
                await _send_busy(scope, send, retry_after)
                return

            # Wait (briefly) for a slot. A cheap burst frees slots within
            # milliseconds so waiters drain; a heavy flood holds them past
            # queue_wait and the waiter is shed. (Py3.12 cancels acquire cleanly
            # on timeout, so no semaphore leak.)
            _waiters += 1
            try:
                await asyncio.wait_for(_sem.acquire(), timeout=queue_wait)
            except asyncio.TimeoutError:
                await _send_busy(scope, send, retry_after)
                return
            finally:
                _waiters -= 1

            try:
                await app(scope, receive, send)
            finally:
                _sem.release()

        return inner

    return wrap
