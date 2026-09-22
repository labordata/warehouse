"""Retire the per-row pages (/<db>/<table>/<pk>) and stop linking to them.

On 2026-09-22 a rotating residential-proxy crawler (real headless Chrome that
solves Cloudflare's managed challenge, spread across many ASNs) walked
osha_enforcement row pages and drained the machine's CPU-credit bank: in the
hour the bank drained, row pages were 90% of origin time. Row pages get almost
no human use -- over the 8 days before, ~40k row-page 200s had 3 external
referers; the rest were crawlers following in-site links -- so they are
retired rather than defended. The edge (Cloudflare) returns 410 for the same
paths; this is the origin-side backstop plus the link cleanup that keeps
table pages from pointing at dead URLs.

Three parts:

  - asgi_wrapper: 410 Gone for /<db>/<table>/<pk> and /<db>/<table>/<pk>.<fmt>
    when <db> (or its hash-suffixed form, <db>-<hash>) is a mounted database.
    Any path with a `-` segment (/db/-/query, /db/table/-/..., /-/static/...)
    is left alone, as are two-segment table/canned-query paths.
  - render_cell: an expanded foreign-key cell links to the referenced table
    filtered on the key (/db/other_table?other_column=value) instead of to the
    referenced row's page. Same record, reached through a table page.
  - templates/_table.html renders the primary-key cell as plain text instead
    of a link to the row page.
"""
from urllib.parse import quote, urlencode

import markupsafe
from datasette import hookimpl

GONE_BODY = (
    b"410 Gone: per-row pages are no longer served. "
    b"Browse or filter the table instead, e.g. /<database>/<table>?<column>=<value>\n"
)


def _is_row_path(path, databases):
    parts = [p for p in path.split("/") if p]
    if len(parts) != 3 or "-" in parts:
        return False
    db = parts[0]
    return any(db == name or db.startswith(name + "-") for name in databases)


@hookimpl
def asgi_wrapper(datasette):
    def wrap(app):
        async def wrapped(scope, receive, send):
            if scope.get("type") == "http" and _is_row_path(
                scope.get("path", ""), datasette.databases
            ):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 410,
                        "headers": [
                            [b"content-type", b"text/plain; charset=utf-8"],
                            [b"cache-control", b"public, max-age=86400"],
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": GONE_BODY})
                return
            await app(scope, receive, send)

        return wrapped

    return wrap


@hookimpl
def render_cell(value, column, table, database, datasette):
    # Expanded foreign keys arrive as {"value": ..., "label": ...}.
    if not (isinstance(value, dict) and "value" in value and table):
        return None

    async def inner():
        fks = await datasette.get_database(database).foreign_keys_for_table(table)
        fk = next((fk for fk in fks if fk["column"] == column), None)
        if fk is None:
            return None
        raw, label = value["value"], value.get("label")
        href = "{}?{}".format(
            datasette.urls.table(database, fk["other_table"]),
            urlencode({fk["other_column"]: raw}, quote_via=quote),
        )
        id_ = markupsafe.escape(raw)
        if label is not None and str(label) != str(raw):
            return markupsafe.Markup(
                '<a href="{}">{}</a>&nbsp;<em>{}</em>'.format(
                    markupsafe.escape(href), markupsafe.escape(label) or "-", id_
                )
            )
        return markupsafe.Markup(
            '<a href="{}">{}</a>'.format(markupsafe.escape(href), id_)
        )

    return inner
