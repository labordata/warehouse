import re
from xml.sax.saxutils import escape

from datasette import hookimpl
from datasette.utils.asgi import Response

INTERNAL_DATABASES = {"_internal", "_memory"}

# A trailing timezone designator: Z or ±hh:mm / ±hhmm.
_HAS_TZ = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")


def _iso_datetime(value):
    """Normalize a date/datetime scalar to a sitemap-valid W3C datetime.

    Per the sitemaps spec <lastmod> must be either a date (YYYY-MM-DD) or a
    *full* datetime carrying a timezone. The warehouse hands us naive UTC
    timestamps like '2026-04-22 17:14:37' (no zone), which Search Console
    rejects as an invalid date. So: swap the separator, drop any fractional
    seconds, and stamp UTC — while leaving date-only and already-zoned values
    untouched.
    """
    s = str(value).strip()
    if not s:
        return None
    s = s.replace(" ", "T", 1)
    if "T" not in s:
        return s  # date-only is already valid
    if _HAS_TZ.search(s):
        return s  # already carries a timezone
    return s.split(".", 1)[0] + "Z"


async def _db_lastmod(datasette, name, db):
    """Per-database freshness from the `date_modified_sql` metadata key.

    Mirrors datasette-schema-org's dateModified so the sitemap and the
    structured data agree. Operator-supplied SQL (not user input); failures
    degrade to no <lastmod> rather than breaking the sitemap.
    """
    meta = await datasette.get_database_metadata(name)
    sql = (meta or {}).get("date_modified_sql")
    if not sql:
        return None
    try:
        row = (await db.execute(sql)).first()
    except Exception:
        return None
    if not row or row[0] is None:
        return None
    return _iso_datetime(row[0])


async def sitemap(request, datasette):
    scheme = "https" if datasette.setting("force_https_urls") else request.scheme
    base = f"{scheme}://{request.host}"
    # Each entry is (loc, lastmod-or-None).
    entries: list[tuple[str, str | None]] = [(f"{base}/", None)]
    for name, db in datasette.databases.items():
        if name in INTERNAL_DATABASES:
            continue
        lastmod = await _db_lastmod(datasette, name, db)
        entries.append((f"{base}/{name}", lastmod))
        entries.append((f"{base}/{name}.db", lastmod))
        hidden = set(await db.hidden_table_names())
        for table in await db.table_names():
            if table in hidden or table.startswith("sqlite_"):
                continue
            entries.append((f"{base}/{name}/{table}", lastmod))
    body = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, lastmod in entries:
        if lastmod:
            body.append(
                f"  <url><loc>{escape(loc)}</loc>"
                f"<lastmod>{escape(lastmod)}</lastmod></url>"
            )
        else:
            body.append(f"  <url><loc>{escape(loc)}</loc></url>")
    body.append("</urlset>")
    return Response("\n".join(body), content_type="application/xml")


@hookimpl
def register_routes():
    return [(r"^/sitemap\.xml$", sitemap)]
