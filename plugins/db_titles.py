"""Expose per-database titles to the index template.

Datasette doesn't surface per-db metadata in the index context — `metadata`
holds top-level keys only, and the `database` objects don't carry their
title. This plugin runs once per index render and looks up each visible
database's `metadata.databases.<name>.title` from warehouse_metadata.yml,
exposing it as `db_titles[db.name]` to templates/index.html.
"""

from datasette import hookimpl


@hookimpl
def extra_template_vars(template, datasette):
    if template != "index.html":
        return None

    async def inner():
        titles = {}
        for db_name in datasette.databases:
            md = await datasette.get_database_metadata(db_name)
            title = (md or {}).get("title")
            if title:
                titles[db_name] = title
        return {"db_titles": titles}

    return inner
