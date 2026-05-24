from xml.sax.saxutils import escape

from datasette import hookimpl
from datasette.utils.asgi import Response

INTERNAL_DATABASES = {"_internal", "_memory"}


def _iso_datetime(value):
    """Normalize a SQLite date/datetime scalar to ISO 8601 for <lastmod>."""
    s = str(value).strip()
    if not s:
        return None
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)
    return s


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
