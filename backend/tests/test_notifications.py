import pytest
from marketing_backend.notifications import retry_delay_seconds


@pytest.mark.parametrize(
    "attempt, expected",
    [
        (1, 30),
        (2, 60),
        (3, 120),
        (4, 240),
        (5, 480),
        (10, 3600),
        (20, 3600),
    ],
)
def test_notification_retry_delay(attempt, expected):
    assert retry_delay_seconds(attempt) == expected


def test_retry_delay_rejects_invalid_attempt():
    with pytest.raises(ValueError):
        retry_delay_seconds(0)
from marketing_backend.notifications import (
    NtfyConfig,
    NtfyTransport,
    FakeNtfyTransport,
)


def test_notifications_disabled_by_default(monkeypatch):
    monkeypatch.delenv("NTFY_ENABLED", raising=False)
    monkeypatch.delenv("NTFY_SERVER_URL", raising=False)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.delenv("NTFY_AUTH_TOKEN", raising=False)

    config = NtfyConfig.from_env()

    assert config.enabled is False
    assert config.server_url == ""
    assert config.topic == ""
    assert config.auth_token == ""


def test_disabled_transport_does_not_send():
    config = NtfyConfig(
        enabled=False,
        server_url="",
        topic="",
    )

    transport = NtfyTransport(config)

    assert transport.send_approval_alert() is False


def test_fake_transport_records_approval_alert():
    transport = FakeNtfyTransport()

    result = transport.send_approval_alert()

    assert result is True
    assert transport.sent_alerts == [
        "A new outreach draft is waiting for your review."
    ]


def test_enabled_transport_requires_server_and_topic():
    config = NtfyConfig(
        enabled=True,
        server_url="",
        topic="",
    )

    transport = NtfyTransport(config)

    with pytest.raises(ValueError):
        transport.send_approval_alert()
def test_enabled_transport_sends_generic_alert_without_network(monkeypatch):
    config = NtfyConfig(
        enabled=True,
        server_url="https://ntfy.example.com",
        topic="review-alerts",
        auth_token="test-token",
    )

    class FakeResponse:
        def raise_for_status(self):
            return None

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(
        "marketing_backend.notifications.httpx.post",
        fake_post,
    )

    transport = NtfyTransport(config)
    result = transport.send_approval_alert()

    assert result is True
    assert captured["url"] == "https://ntfy.example.com/review-alerts"
    assert captured["content"] == (
        "A new outreach draft is waiting for your review."
    )
    assert captured["headers"]["Authorization"] == "Bearer test-token"
    assert captured["timeout"] == 10.0
def test_http_error_is_not_reported_as_success(monkeypatch):
    import httpx

    config = NtfyConfig(
        enabled=True,
        server_url="https://ntfy.example.com",
        topic="review-alerts",
    )

    def fake_post(url, **kwargs):
        request = httpx.Request("POST", url)
        response = httpx.Response(503, request=request)
        return response

    monkeypatch.setattr(
        "marketing_backend.notifications.httpx.post",
        fake_post,
    )

    transport = NtfyTransport(config)

    with pytest.raises(httpx.HTTPStatusError):
        transport.send_approval_alert()
def test_enabled_configuration_loads_environment(monkeypatch):
    monkeypatch.setenv("NTFY_ENABLED", "true")
    monkeypatch.setenv("NTFY_SERVER_URL", "https://ntfy.example.com/")
    monkeypatch.setenv("NTFY_TOPIC", "review-alerts")
    monkeypatch.setenv("NTFY_AUTH_TOKEN", "test-token")

    config = NtfyConfig.from_env()

    assert config.enabled is True
    assert config.server_url == "https://ntfy.example.com"
    assert config.topic == "review-alerts"
    assert config.auth_token == "test-token"