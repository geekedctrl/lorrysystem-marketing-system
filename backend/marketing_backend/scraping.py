"""Readable company evidence with guarded, bounded optional browser rendering."""

import os
import time
from urllib.parse import urlsplit
from trafilatura import extract
from .public_fetch import fetch_public, checked_url, FetchError


def readable(body):
    return " ".join(
        (extract(body, include_tables=True, include_comments=False) or "").split()
    )[:12000]


def render_public(url):
    """All browser traffic is fulfilled by the DNS-pinned, robots-aware fetcher.

    No browser direct HTTP, WebSockets, cookies, POSTs or service workers. This
    fallback is opt-in because Chromium adds a worker installation requirement.
    """
    try:
        from playwright.sync_api import sync_playwright, Error
    except ImportError:
        raise FetchError("BROWSER_UNAVAILABLE") from None

    checked_url(url)
    host = urlsplit(url).hostname
    deadline = time.monotonic() + 30
    budget = {"requests": 0, "bytes": 0}
    allowed = (
        "text/html",
        "application/xhtml+xml",
        "text/plain",
        "application/javascript",
        "text/javascript",
        "application/json",
        "text/css",
    )

    def intercept(route):
        request = route.request
        if (
            request.method != "GET"
            or urlsplit(request.url).hostname != host
            or request.resource_type
            not in {"document", "script", "xhr", "fetch", "stylesheet"}
            or budget["requests"] >= 20
            or budget["bytes"] >= 2_000_000
            or time.monotonic() >= deadline
        ):
            route.abort()
            return
        budget["requests"] += 1
        try:
            result = fetch_public(
                request.url, content_types=allowed, allowed_hosts={host}
            )
            if (
                result["fetch_status"] != "SUCCESS"
                or urlsplit(result["final_url"]).hostname != host
            ):
                route.abort()
                return
            body = result["body"]
            size = len(body.encode())
            if budget["bytes"] + size > 2_000_000:
                route.abort()
                return
            budget["bytes"] += size
            route.fulfill(status=200, body=body, content_type=result["content_type"])
        except FetchError:
            route.abort()

    try:
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(
                headless=True, args=["--disable-background-networking"]
            )
            try:
                context = browser.new_context(
                    service_workers="block", accept_downloads=False
                )
                context.route("**/*", intercept)
                context.route_web_socket("**/*", lambda socket: socket.close())
                tab = context.new_page()
                context.on(
                    "page", lambda other: other.close() if other != tab else None
                )
                tab.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Allow a bounded interval for client rendering; network-idle can never settle.
                tab.wait_for_timeout(1500)
                if tab.url != url:
                    raise FetchError("BROWSER_NAVIGATION_CHANGED")
                return tab.content()[:500000]
            finally:
                browser.close()
    except (Error, ImportError):
        raise FetchError("BROWSER_UNAVAILABLE") from None


def browser_enabled():
    return os.getenv("DISCOVERY_BROWSER_FALLBACK", "false").lower() == "true"
