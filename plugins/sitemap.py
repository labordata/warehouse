from xml.sax.saxutils import escape

from datasette import hookimpl
from datasette.utils.asgi import Response

INTERNAL_DATABASES = {"_internal", "_memory"}


async def sitemap(request, datasette):
    scheme = "https" if datasette.setting("force_https_urls") else request.scheme
    base = f"{scheme}://{request.host}"
    urls = [f"{base}/"]
    for name, db in datasette.databases.items():
        if name in INTERNAL_DATABASES:
            continue
        urls.append(f"{base}/{name}")
        urls.append(f"{base}/{name}.db")
        hidden = set(await db.hidden_table_names())
        for table in await db.table_names():
            if table in hidden or table.startswith("sqlite_"):
                continue
            urls.append(f"{base}/{name}/{table}")
    body = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in urls:
        body.append(f"  <url><loc>{escape(url)}</loc></url>")
    body.append("</urlset>")
    return Response("\n".join(body), content_type="application/xml")


@hookimpl
def register_routes():
    return [(r"^/sitemap\.xml$", sitemap)]
