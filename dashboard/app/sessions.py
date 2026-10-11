"""Signed sessions that do not overwrite newer cookies on read-only responses."""
from copy import deepcopy

from starlette.middleware.sessions import SessionMiddleware

SESSION_COOKIE = "marketing_dashboard_session"
_INITIAL_SESSION = "marketing.initial_session"


class StableSessionMiddleware(SessionMiddleware):
    def __init__(self, app, **kwargs):
        async def snapshot_app(scope, receive, send):
            if scope["type"] in ("http", "websocket"):
                scope[_INITIAL_SESSION] = deepcopy(scope["session"])
            await app(scope, receive, send)

        super().__init__(snapshot_app, **kwargs)

    async def __call__(self, scope, receive, send):
        async def send_changes_only(message):
            if (
                message["type"] == "http.response.start"
                and _INITIAL_SESSION in scope
                and scope["session"] == scope[_INITIAL_SESSION]
            ):
                # Starlette re-signs every nonempty session, even on static GETs.
                # An older response arriving late can restore a pre-login cookie.
                # Keep other cookies; only omit our unchanged session write.
                prefix = (self.session_cookie + "=").encode("latin-1")
                message = {
                    **message,
                    "headers": [
                        (name, value)
                        for name, value in message.get("headers", [])
                        if not (name.lower() == b"set-cookie" and value.startswith(prefix))
                    ],
                }
            await send(message)

        await super().__call__(scope, receive, send_changes_only)
