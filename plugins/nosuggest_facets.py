"""Skip facet *suggestion* on databases whose tables are too wide for it.

Datasette suggests facets by running one grouped query per column. On the
Parquet-backed `usaspending` views that is ~30ms x 293 columns ~ 10-18s per
page on shared-cpu-1x, and it dominates page time (the page itself renders in
~0.5s). The cost is per-query Parquet decode overhead, so it does not go away
by consolidating files or raising time limits -- only by not running 293 of
them.

Datasette already honours `?_nosuggest=1` per request, but has no per-database
setting, and turning `suggest_facets` off globally would take suggestions away
from the narrow native tables where they are cheap (~0.15s) and useful. So
this sets `_nosuggest` on the way in, for configured databases only.

Explicit faceting is untouched: `?_facet=awarding_agency_name` still works, and
any `facets:` configured in metadata still render. Only the automatic
"suggested facets" links are skipped.

    plugins:
      nosuggest-facets:
        databases: [usaspending]
"""
from datasette import hookimpl


@hookimpl
def asgi_wrapper(datasette):
    def wrap(app):
        async def wrapped(scope, receive, send):
            if scope.get("type") == "http":
                config = datasette.plugin_config("nosuggest-facets") or {}
                databases = config.get("databases") or []
                path = scope.get("path", "")
                # /<database>/<table>... -- only table pages suggest facets
                parts = [p for p in path.split("/") if p]
                if len(parts) >= 2 and parts[0] in databases:
                    query = scope.get("query_string", b"")
                    if b"_nosuggest" not in query:
                        scope = dict(scope)
                        scope["query_string"] = (
                            query + b"&_nosuggest=1" if query else b"_nosuggest=1"
                        )
            await app(scope, receive, send)

        return wrapped

    return wrap
