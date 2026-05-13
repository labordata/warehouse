"""Inject schema.org Dataset JSON-LD into each database overview page."""

import json
import re

from datasette import hookimpl

INTERNAL_DATABASES = {"_internal", "_memory"}
_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_END_RE = re.compile(r"</(p|li|h\d|br|div)>", re.IGNORECASE)


def strip_html(text):
    if not text:
        return ""
    text = _BLOCK_END_RE.sub(" ", text)
    text = _TAG_RE.sub("", text)
    return " ".join(text.split())


@hookimpl
def extra_template_vars(template, database, table, view_name, request, datasette):
    if view_name != "database" or not database or database in INTERNAL_DATABASES:
        return None

    async def inner():
        db_meta = (datasette.metadata("databases") or {}).get(database) or {}

        scheme = "https" if datasette.setting("force_https_urls") else request.scheme
        base = f"{scheme}://{request.host}"

        jsonld = {
            "@context": "https://schema.org/",
            "@type": "Dataset",
            "name": db_meta.get("title") or database,
            "url": f"{base}/{database}",
            "distribution": [
                {
                    "@type": "DataDownload",
                    "encodingFormat": "application/x-sqlite3",
                    "contentUrl": f"{base}/{database}.db",
                },
                {
                    "@type": "DataDownload",
                    "encodingFormat": "application/json",
                    "contentUrl": f"{base}/{database}.json",
                },
            ],
        }

        description = db_meta.get("description") or strip_html(db_meta.get("description_html", ""))
        if description:
            jsonld["description"] = description

        if db_meta.get("source"):
            isbasedon = {"@type": "CreativeWork", "name": db_meta["source"]}
            if db_meta.get("source_url"):
                isbasedon["url"] = db_meta["source_url"]
            jsonld["isBasedOn"] = isbasedon

        plugin_config = datasette.plugin_config("schema-org") or {}
        if plugin_config.get("creator"):
            jsonld["creator"] = plugin_config["creator"]
        if plugin_config.get("license"):
            jsonld["license"] = plugin_config["license"]

        keywords = list(plugin_config.get("keywords") or [])
        for k in db_meta.get("keywords") or []:
            if k not in keywords:
                keywords.append(k)
        if keywords:
            jsonld["keywords"] = keywords

        return {
            "schema_org_jsonld": '<script type="application/ld+json">\n{}\n</script>'.format(
                json.dumps(jsonld, indent=2)
            )
        }

    return inner
