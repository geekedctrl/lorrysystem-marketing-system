
"""Guarded public webpage fetch utility for the Marketing API.

No database operations, browser automation, cookies, or private-network access.
"""

import http.client
import ipaddress
import re
import socket
import ssl
import threading
import time

from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser


AGENT = "LorrySystemResearchBot/0.1"
USER_AGENT = AGENT + " (public company information; no authentication)"

MAX_BODY_BYTES = 262144
MAX_ROBOTS_BYTES = 65536
MAX_REDIRECTS = 2
REQUEST_TIMEOUT = 8

ALLOWED_CONTENT_TYPES = (
    "text/html",
    "text/plain",
    "application/xhtml+xml",
)

DISALLOWED_TLDS = (
    "local", "localhost", "internal", "lan",
    "home", "onion", "test", "invalid",
    "example", "arpa",
)

LABEL = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)

ROBOTS_CACHE = {}
ROBOTS_LOCK = threading.Lock()


class FetchError(Exception):
    def __init__(self, reason, status=None):
        self.reason = reason
        self.status = status
        super().__init__(reason)


# ============================================================
# URL Validation
# ============================================================

def checked_url(value):

    if (
        not isinstance(value, str)
        or len(value) > 1500
        or re.search(r"[\x00-\x20\x7f]", value)
    ):
        raise FetchError("INVALID_URL")

    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port

    except (ValueError, AttributeError):
        raise FetchError("INVALID_URL")

    if (
        parsed.scheme not in ("http", "https")
        or not host
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise FetchError("UNSAFE_URL")

    if parsed.netloc.endswith("."):
        raise FetchError("UNSAFE_URL")

    try:
        host = host.encode("idna").decode("ascii").lower()

    except UnicodeError:
        raise FetchError("UNSAFE_HOST")

    if (
        len(host) > 253
        or "." not in host
        or any(
            not LABEL.fullmatch(label)
            for label in host.split(".")
        )
    ):
        raise FetchError("UNSAFE_HOST")

    # Reject direct IP addresses.
    try:
        ipaddress.ip_address(host)
        raise FetchError("IP_LITERAL_DENIED")

    except ValueError:
        pass

    if host.split(".")[-1] in DISALLOWED_TLDS:
        raise FetchError("PRIVATE_HOST_DENIED")

    expected_port = (
        443 if parsed.scheme == "https" else 80
    )

    if port not in (None, expected_port):
        raise FetchError("NONSTANDARD_PORT_DENIED")

    path = parsed.path or "/"

    safe_url = urlunsplit((
        parsed.scheme,
        host,
        path,
        parsed.query,
        "",
    ))

    request_path = path

    if parsed.query:
        request_path += "?" + parsed.query

    return (
        safe_url,
        parsed.scheme,
        host,
        expected_port,
        request_path,
    )


# ============================================================
# DNS / SSRF Protection
# ============================================================

def pinned_address(host, port):

    try:
        records = socket.getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
        )

    except (socket.gaierror, OSError):
        raise FetchError("DNS_ERROR")

    if not records:
        raise FetchError("DNS_ERROR")

    choices = []

    for family, _, _, _, sockaddr in records:

        if family not in (
            socket.AF_INET,
            socket.AF_INET6,
        ):
            continue

        ip = ipaddress.ip_address(
            sockaddr[0].split("%")[0]
        )

        if (
            not ip.is_global
            or ip.is_multicast
            or ip.is_reserved
        ):
            raise FetchError(
                "NONPUBLIC_DNS_ADDRESS"
            )

        choices.append((family, str(ip)))

    if not choices:
        raise FetchError("DNS_ERROR")

    # Prefer IPv4 if available.
    choices.sort(
        key=lambda item: item[0] != socket.AF_INET
    )

    return choices[0][1]


# ============================================================
# Pinned HTTP Connections
# ============================================================

class PinnedHTTP(http.client.HTTPConnection):

    def __init__(self, host, port, address):

        super().__init__(
            host,
            port,
            timeout=REQUEST_TIMEOUT,
        )

        self.address = address

    def connect(self):

        self.sock = socket.create_connection(
            (self.address, self.port),
            timeout=self.timeout,
        )


class PinnedHTTPS(http.client.HTTPSConnection):

    def __init__(self, host, port, address):

        super().__init__(
            host,
            port,
            timeout=REQUEST_TIMEOUT,
            context=ssl.create_default_context(),
        )

        self.address = address

    def connect(self):

        raw = socket.create_connection(
            (self.address, self.port),
            timeout=self.timeout,
        )

        try:
            # Connect to the checked IP while verifying
            # the TLS certificate against the original hostname.
            self.sock = self._context.wrap_socket(
                raw,
                server_hostname=self.host,
            )

        except BaseException:
            raw.close()
            raise


# ============================================================
# Single HTTP Request
# ============================================================

def request_once(url, byte_limit):

    (
        safe_url,
        scheme,
        host,
        port,
        path,
    ) = checked_url(url)

    address = pinned_address(host, port)

    if scheme == "https":
        connection = PinnedHTTPS(
            host,
            port,
            address,
        )

    else:
        connection = PinnedHTTP(
            host,
            port,
            address,
        )

    try:

        connection.request(
            "GET",
            path,
            headers={
                "Host": host,
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,text/plain,"
                    "application/xhtml+xml"
                ),
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
        )

        response = connection.getresponse()

        content_type = response.getheader(
            "Content-Type",
            "",
        )

        content_encoding = response.getheader(
            "Content-Encoding",
            "identity",
        ).lower()

        location = response.getheader(
            "Location"
        )

        status = response.status

        if content_encoding not in ("", "identity"):
            raise FetchError(
                "COMPRESSED_RESPONSE_DENIED",
                status,
            )

        # Never download unlimited response bodies.
        body = response.read(byte_limit + 1)

        return {
            "url": safe_url,
            "status": status,
            "content_type": content_type,
            "location": location,
            "body": body[:byte_limit],
            "truncated": len(body) > byte_limit,
            "bytes_read": len(body[:byte_limit]),
        }

    except (TimeoutError, socket.timeout):
        raise FetchError("TIMEOUT")

    except ssl.SSLError:
        raise FetchError("TLS_ERROR")

    except (
        ConnectionError,
        http.client.HTTPException,
        OSError,
    ):
        raise FetchError("CONNECTION_ERROR")

    finally:
        connection.close()


# ============================================================
# robots.txt
# ============================================================

def robots_permission(url):

    _, scheme, host, _, _ = checked_url(url)

    cache_key = scheme + "://" + host

    with ROBOTS_LOCK:

        cached = ROBOTS_CACHE.get(cache_key)

        if cached and cached[0] > time.monotonic():
            rule = cached[1]

        else:
            rule = None

    if rule is None:

        robots_url = cache_key + "/robots.txt"

        # Fail closed when robots.txt cannot be evaluated.
        for _ in range(2):

            result = request_once(
                robots_url,
                MAX_ROBOTS_BYTES,
            )

            if (
                result["status"] in (301, 302, 307, 308)
                and result["location"]
            ):

                following = urljoin(
                    robots_url,
                    result["location"],
                )

                _, next_scheme, next_host, _, _ = (
                    checked_url(following)
                )

                if (
                    next_scheme != scheme
                    or next_host != host
                ):
                    raise FetchError(
                        "ROBOTS_REDIRECT_UNSAFE"
                    )

                robots_url = following
                continue

            if result["status"] in (404, 410):

                rule = True

            elif result["status"] in (401, 403, 429):

                rule = False

            elif (
                result["status"] == 200
                and not result["truncated"]
            ):

                parser = RobotFileParser()

                parser.parse(
                    result["body"]
                    .decode(
                        "utf-8",
                        errors="replace",
                    )
                    .splitlines()
                )

                rule = parser

            else:

                raise FetchError(
                    "ROBOTS_UNAVAILABLE"
                )

            break

        if rule is None:
            raise FetchError(
                "ROBOTS_UNAVAILABLE"
            )

        with ROBOTS_LOCK:

            ROBOTS_CACHE[cache_key] = (
                time.monotonic() + 900,
                rule,
            )

    if (
        rule is False
        or (
            rule is not True
            and not rule.can_fetch(AGENT, url)
        )
    ):
        raise FetchError(
            "ROBOTS_DISALLOWED"
        )


# ============================================================
# Main Public Fetch Function
# ============================================================

def fetch_public(target):

    current, _, _, _, _ = checked_url(target)

    visited = set()

    previous_scheme = None
    redirects = 0

    for hop in range(MAX_REDIRECTS + 1):

        checked, scheme, _, _, _ = (
            checked_url(current)
        )

        if checked in visited:
            raise FetchError("REDIRECT_LOOP")

        visited.add(checked)

        if (
            previous_scheme == "https"
            and scheme == "http"
        ):
            raise FetchError(
                "HTTPS_DOWNGRADE_DENIED"
            )

        # Respect robots.txt before requesting the page.
        robots_permission(checked)

        result = request_once(
            checked,
            MAX_BODY_BYTES,
        )

        status = result["status"]

        # Follow redirects safely.
        if status in (301, 302, 303, 307, 308):

            if not result["location"]:
                raise FetchError(
                    "REDIRECT_WITHOUT_LOCATION",
                    status,
                )

            if hop >= MAX_REDIRECTS:
                raise FetchError(
                    "REDIRECT_LIMIT",
                    status,
                )

            following = urljoin(
                checked,
                result["location"],
            )

            # Validate every redirect destination.
            checked_url(following)

            previous_scheme = scheme
            current = following

            redirects += 1
            continue

        common = {
            "url": target,
            "final_url": checked,
            "http_status": status,
            "content_type": result["content_type"],
            "redirect_count": redirects,
            "bytes_read": result["bytes_read"],
            "truncated": result["truncated"],
        }

        if status in (401, 403, 429):

            return dict(
                common,
                fetch_status="BLOCKED",
                failure_reason=(
                    "RATE_LIMITED"
                    if status == 429
                    else "HTTP_" + str(status)
                ),
                body="",
            )

        if status < 200 or status >= 300:

            return dict(
                common,
                fetch_status="FAILED",
                failure_reason="HTTP_" + str(status),
                body="",
            )

        mime = (
            result["content_type"]
            .split(";", 1)[0]
            .strip()
            .lower()
        )

        if mime not in ALLOWED_CONTENT_TYPES:

            return dict(
                common,
                fetch_status="FAILED",
                failure_reason="UNSUPPORTED_CONTENT_TYPE",
                body="",
            )

        if not result["body"]:

            return dict(
                common,
                fetch_status="FAILED",
                failure_reason="EMPTY_BODY",
                body="",
            )

        # No JavaScript execution or CAPTCHA bypass.
        body = result["body"].decode(
            "utf-8",
            errors="replace",
        )

        return dict(
            common,
            fetch_status="SUCCESS",
            failure_reason=None,
            body=body,
        )

    raise FetchError("REDIRECT_LIMIT")
