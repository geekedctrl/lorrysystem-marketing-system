"""Reviewer approval notifications using ntfy.

Notifications are disabled by default.
This module never sends prospect outreach messages.
"""

import logging
import os
from dataclasses import dataclass

import httpx

log = logging.getLogger("marketing-notifications")


@dataclass(frozen=True)
class NtfyConfig:
    enabled: bool
    server_url: str
    topic: str
    auth_token: str = ""

    @classmethod
    def from_env(cls):
        return cls(
            enabled=os.getenv("NTFY_ENABLED", "false").lower() == "true",
            server_url=os.getenv("NTFY_SERVER_URL", "").rstrip("/"),
            topic=os.getenv("NTFY_TOPIC", ""),
            auth_token=os.getenv("NTFY_AUTH_TOKEN", ""),
        )


class NtfyTransport:
    """Sends a generic reviewer alert to a configured ntfy topic."""

    def __init__(self, config: NtfyConfig):
        self.config = config

    def send_approval_alert(self):
        if not self.config.enabled:
            return False

        if not self.config.server_url or not self.config.topic:
            raise ValueError("NTFY server URL and topic are required when enabled")

        url = f"{self.config.server_url}/{self.config.topic}"

        headers = {
            "Title": "Marketing System: Approval required",
            "Priority": "default",
        }

        if self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"

        response = httpx.post(
            url,
            content="A new outreach draft is waiting for your review.",
            headers=headers,
            timeout=10.0,
        )
        response.raise_for_status()
        return True


class FakeNtfyTransport:
    """Test transport. It never makes a network request."""

    def __init__(self):
        self.sent_alerts = []

    def send_approval_alert(self):
        self.sent_alerts.append(
            "A new outreach draft is waiting for your review."
        )
        return True


def send_approval_alert_if_enabled():
    """Send an approval alert without changing the persisted decision."""
    try:
        return NtfyTransport(NtfyConfig.from_env()).send_approval_alert()
    except (httpx.HTTPError, ValueError):
        log.exception("Approval notification delivery failed")
        return False


def retry_delay_seconds(
    attempt: int,
    base_delay_seconds: int = 30,
    max_delay_seconds: int = 3600,
) -> int:
    """Calculate exponential retry delay, capped at one hour."""

    if attempt < 1:
        raise ValueError("Attempt must be at least 1")

    if base_delay_seconds < 1:
        raise ValueError("Base delay must be positive")

    if max_delay_seconds < base_delay_seconds:
        raise ValueError("Maximum delay cannot be smaller than base delay")

    delay = base_delay_seconds

    for _ in range(attempt - 1):
        delay = min(delay * 2, max_delay_seconds)

        if delay == max_delay_seconds:
            break

    return delay
