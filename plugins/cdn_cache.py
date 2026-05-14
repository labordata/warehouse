"""Edge-cache friendly headers for Datasette.

Sets Cache-Control (browser, short TTL) and CDN-Cache-Control
(Cloudflare/CDN, long TTL) on responses that can be served from cache.

Pairs with a deploy-time Cloudflare purge: edge content lives forever
until a deploy invalidates it. Between deploys, edge serves ~100% of
traffic; origin only sees uncached or admin paths.

Also handles legacy /db-<hash>/... URLs from the previous
datasette-hashed-urls regime: they 301 to the unhashed canonical form.
External links indexed under old hashes continue to resolve.

Skips:
  - non-GET/HEAD requests
  - /-/ admin paths and /static
  - paths that don't resolve to a known database (favicon, etc.)
  - non-2xx responses

No ETag emission: Cloudflare's on-the-fly compression strips ETags
that aren't matched by an origin-supplied Content-Encoding. The
browser-side 304 path isn't worth the cost of origin compression.
"""

import re

from datasette import hookimpl

INTERNAL_DATABASES = {"_internal", "_memory"}
SHORT_MAX_AGE = 60
LONG_MAX_AGE = 31_536_000
_HASH_SUFFIX = re.compile(r"-[a-f0-9]{6,16}$")


def _split_first(path):
    parts = path.lstrip("/").split("/", 1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


def _split_format(first):
    name, dot, fmt = first.partition(".")
    return name, (("." + fmt) if dot else "")


def _classify(datasette, path):
    """Return 'cache', ('redirect', new_path), or 'skip'."""
    first, rest = _split_first(path)
    if not first:
        return "cache"

    name, fmt = _split_format(first)

    if name in INTERNAL_DATABASES:
        return "skip"

    if name in datasette.databases:
        return "cache"

    m = _HASH_SUFFIX.search(name)
    if m:
        candidate = name[: m.start()]
        if candidate in datasette.databases:
            new_first = candidate + fmt
            new_path = "/" + new_first + (("/" + rest) if rest else "")
            return ("redirect", new_path)

    return "skip"


_CACHE_HEADERS = (
    (b"cache-control", f"public, max-age={SHORT_MAX_AGE}".encode()),
    (b"cdn-cache-control", f"public, max-age={LONG_MAX_AGE}".encode()),
)
_STRIP = {b"cache-control", b"cdn-cache-control"}


async def _send_redirect(send, new_path, query):
    location = new_path
    if query:
        location += "?" + query.decode("latin-1")
    await send(
        {
            "type": "http.response.start",
            "status": 301,
            "headers": [
                (b"location", location.encode("latin-1")),
                (b"cache-control", f"public, max-age={LONG_MAX_AGE}".encode()),
                (b"cdn-cache-control", f"public, max-age={LONG_MAX_AGE}".encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": b""})


@hookimpl
def asgi_wrapper(datasette):
    def wrap(app):
        async def inner(scope, receive, send):
            if scope.get("type") != "http" or scope.get("method") not in ("GET", "HEAD"):
                await app(scope, receive, send)
                return

            path = scope.get("path", "/")
            if path.startswith("/-/") or path.startswith("/static/"):
                await app(scope, receive, send)
                return

            verdict = _classify(datasette, path)

            if isinstance(verdict, tuple) and verdict[0] == "redirect":
                await _send_redirect(send, verdict[1], scope.get("query_string", b""))
                return

            if verdict != "cache":
                await app(scope, receive, send)
                return

            async def wrapped_send(message):
                if message["type"] == "http.response.start":
                    status = message.get("status", 200)
                    if 200 <= status < 300:
                        headers = [
                            (k, v)
                            for k, v in message.get("headers", [])
                            if k.lower() not in _STRIP
                        ]
                        headers.extend(_CACHE_HEADERS)
                        message = {**message, "headers": headers}
                await send(message)

            await app(scope, receive, wrapped_send)

        return inner

    return wrap
