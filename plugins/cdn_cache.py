"""Edge-cache friendly headers for Datasette.

Sets Cache-Control (browser, short TTL) and CDN-Cache-Control
(Cloudflare/CDN, long TTL) on responses that can be served from cache.
Emits a strong ETag derived from the database hash plus a digest of
the request path and query, and short-circuits to 304 Not Modified
when If-None-Match matches.

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

ETag format: strong ("<db-hash>-<digest>"), not weak. Cloudflare's
on-the-fly Brotli compression transforms strong ETags to weak by
adding the W/ prefix and forwards them to clients, whereas
already-weak ETags get dropped through the compression pipeline.
"Respect strong ETags" should remain OFF in the Cloudflare cache
rule so this conversion is allowed to happen.
"""

import hashlib
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


def _root_hash(datasette):
    hashes = sorted(
        db.hash
        for name, db in datasette.databases.items()
        if name not in INTERNAL_DATABASES and db.hash
    )
    if not hashes:
        return None
    return hashlib.sha1("\n".join(hashes).encode("latin-1")).hexdigest()[:12]


def _classify(datasette, path):
    """Return ('cache', db_hash), ('redirect', new_path), or 'skip'."""
    first, rest = _split_first(path)
    if not first:
        h = _root_hash(datasette)
        return ("cache", h) if h else "skip"

    name, fmt = _split_format(first)

    if name in INTERNAL_DATABASES:
        return "skip"

    if name in datasette.databases:
        db = datasette.databases[name]
        if not db.hash:
            return "skip"
        return ("cache", db.hash[:12])

    m = _HASH_SUFFIX.search(name)
    if m:
        candidate = name[: m.start()]
        if candidate in datasette.databases:
            new_first = candidate + fmt
            new_path = "/" + new_first + (("/" + rest) if rest else "")
            return ("redirect", new_path)

    return "skip"


def _make_etag(db_hash, path, query):
    digest = hashlib.sha1(path.encode("latin-1") + b"?" + query).hexdigest()[:10]
    return f'"{db_hash}-{digest}"'


def _request_header(scope, name):
    target = name.lower().encode("latin-1")
    for k, v in scope.get("headers", []):
        if k.lower() == target:
            return v.decode("latin-1")
    return None


def _etag_matches(client_value, our_etag):
    """An If-None-Match value may be the strong tag we sent or the weak
    form Cloudflare produced after transforming it through compression."""
    if not client_value:
        return False
    return client_value == our_etag or client_value == f"W/{our_etag}"


_CACHE_HEADERS = (
    (b"cache-control", f"public, max-age={SHORT_MAX_AGE}".encode()),
    (b"cdn-cache-control", f"public, max-age={LONG_MAX_AGE}".encode()),
)
_STRIP = {b"cache-control", b"cdn-cache-control", b"etag"}


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

            if not (isinstance(verdict, tuple) and verdict[0] == "cache"):
                await app(scope, receive, send)
                return

            db_hash = verdict[1]
            etag = _make_etag(db_hash, path, scope.get("query_string", b""))

            if _etag_matches(_request_header(scope, "if-none-match"), etag):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 304,
                        "headers": [
                            (b"etag", etag.encode("latin-1")),
                            *_CACHE_HEADERS,
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": b""})
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
                        headers.append((b"etag", etag.encode("latin-1")))
                        headers.extend(_CACHE_HEADERS)
                        message = {**message, "headers": headers}
                await send(message)

            await app(scope, receive, wrapped_send)

        return inner

    return wrap
