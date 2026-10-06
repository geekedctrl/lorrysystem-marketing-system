from contextvars import ContextVar

request_auth: ContextVar[dict | None] = ContextVar('request_auth', default=None)
request_icps: ContextVar[list] = ContextVar('request_icps', default=[])
