"""Force CSV responses to download instead of rendering inline.

Datasette only sets Content-Disposition: attachment when the request
includes ?_dl=1. Without it, browsers display CSV as plain text, which
confuses users. This wrapper unconditionally marks any .csv response
as an attachment.
"""

from datasette import hookimpl


@hookimpl
def asgi_wrapper(datasette):
    def wrap(app):
        async def inner(scope, receive, send):
            if scope["type"] != "http" or not scope.get("path", "").endswith(".csv"):
                await app(scope, receive, send)
                return

            filename = scope["path"].rstrip("/").rsplit("/", 1)[-1] or "download.csv"

            async def wrapped_send(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    if not any(name.lower() == b"content-disposition" for name, _ in headers):
                        headers.append(
                            (b"content-disposition", f'attachment; filename="{filename}"'.encode())
                        )
                        message = {**message, "headers": headers}
                await send(message)

            await app(scope, receive, wrapped_send)

        return inner

    return wrap
