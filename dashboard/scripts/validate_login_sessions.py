"""HTTP login/session regressions with a synthetic, mocked account service."""
import base64
import asyncio
import json
import os
from pathlib import Path
import re
import sys
import unittest
import time
from unittest.mock import AsyncMock, patch

root = Path(__file__).resolve().parents[1]
os.chdir(root)
os.environ["DASHBOARD_SESSION_SECRET"] = "synthetic-login-session-secret"
sys.path.insert(0, str(root))

from fastapi.testclient import TestClient
import httpx
from itsdangerous import TimestampSigner
from app import main
from app.api_client import MarketingAPIError
from app import workspace_ui

COOKIE = "marketing_dashboard_session"
ACCOUNT = {"email": "operator@example.test", "password": "synthetic-password"}


def form_token(response):
    return re.search(r'name="csrf_token" value="([^"]+)"', response.text)[1]


class LoginSessionTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app, base_url="https://dashboard.example.test")
        self.post = AsyncMock(return_value={"token": "synthetic-account-token"})
        self.patch = patch.object(main.api, "post", self.post)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.client.close)

    def submit(self, token=None, **kwargs):
        data = dict(ACCOUNT)
        if token is not None:
            data["csrf_token"] = token
        return self.client.post("/login", data=data, follow_redirects=False, **kwargs)

    def assert_recovery(self, response, notice="session-expired"):
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login?notice=" + notice)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.post.assert_not_called()
        refreshed = self.client.get(response.headers["location"])
        self.assertIn(
            "Allow cookies for this site" if notice == "cookies-required"
            else "Please try again using this refreshed form", refreshed.text
        )
        self.assertNotIn(ACCOUNT["password"], refreshed.text)
        # Reload is now a GET, so it cannot repeat the rejected password POST.
        reloaded = self.client.get(response.headers["location"])
        self.assertEqual(form_token(refreshed), form_token(reloaded))
        self.assertEqual(self.submit(form_token(reloaded)).status_code, 303)
        self.post.assert_awaited_once_with(
            "/api/auth/login", json=ACCOUNT, authenticated=False
        )

    def test_fresh_login_sets_dedicated_host_only_cookie_and_rotates_session(self):
        page = self.client.get("/login")
        self.assertEqual(page.status_code, 200)
        cookie = page.headers["set-cookie"].lower()
        self.assertTrue(cookie.startswith(COOKIE + "="))
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        self.assertNotIn("domain=", cookie)
        self.assertEqual(page.headers["cache-control"], "no-store")
        token = form_token(page)
        self.assertEqual(token, form_token(self.client.get("/login")))
        response = self.submit(token)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/dashboard")
        signed = self.client.cookies.get(COOKIE)
        session = json.loads(base64.b64decode(
            TimestampSigner(main.settings.session_secret).unsign(signed)
        ))
        self.assertEqual(session, {"auth_token": "synthetic-account-token"})
        self.assertNotIn(ACCOUNT["password"], signed)

    def test_stale_form_recovers_without_authenticating_rejected_submission(self):
        self.client.get("/login")
        self.assert_recovery(self.submit("stale-form-token"))

    def test_missing_cookie_recovers(self):
        token = form_token(self.client.get("/login"))
        self.client.cookies.clear()
        with patch.object(workspace_ui.logger, "warning") as warning:
            self.assert_recovery(self.submit(token), "cookies-required")
        warning.assert_called_once_with("Login form rejected: reason=%s", "missing_cookie")

    def test_read_only_responses_do_not_reissue_session_cookie(self):
        self.client.get("/login")
        for path in ("/login", "/static/theme.js", "/health"):
            self.assertNotIn("set-cookie", self.client.get(path).headers)

    def test_missing_form_token_recovers(self):
        self.client.get("/login")
        self.assert_recovery(self.submit())

    def test_other_browser_token_cannot_authenticate(self):
        with TestClient(main.app) as other:
            foreign = form_token(other.get("/login"))
        self.client.get("/login")
        self.assert_recovery(self.submit(foreign))

    def test_corrupt_session_recovers(self):
        self.client.cookies.set(COOKIE, "invalid.signature", domain="dashboard.example.test", path="/")
        self.assert_recovery(self.submit("old-form-token"))

    def test_expired_signed_cookie_cannot_authenticate(self):
        old = base64.b64encode(json.dumps({"csrf_token": "expired-token"}).encode())
        signer = TimestampSigner(main.settings.session_secret)
        with patch.object(signer, "get_timestamp", return_value=int(time.time()) - 43201):
            signed = signer.sign(old).decode()
        self.client.cookies.set(COOKIE, signed, domain="dashboard.example.test", path="/")
        with patch.object(workspace_ui.logger, "warning") as warning:
            self.assert_recovery(self.submit("expired-token"))
        warning.assert_called_once_with("Login form rejected: reason=%s", "invalid_or_expired_cookie")

    def test_generic_parent_domain_cookie_cannot_shadow_dashboard_session(self):
        token = form_token(self.client.get("/login"))
        own = self.client.cookies.get(COOKIE)
        for header in (
            f"session=other-app; {COOKIE}={own}; session=another-app",
            f"session=another-app; session=other-app; {COOKIE}={own}",
        ):
            page = self.client.get("/login", headers={"Cookie": header})
            self.assertEqual(form_token(page), token)
        self.assertEqual(self.submit(token).headers["location"], "/dashboard")

    def test_invalid_password_preserves_valid_form_and_never_echoes_password(self):
        self.post.side_effect = MarketingAPIError(401, "Invalid email or password.")
        token = form_token(self.client.get("/login"))
        response = self.submit(token)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Invalid email or password.", response.text)
        self.assertNotIn(ACCOUNT["password"], response.text)
        self.assertEqual(form_token(response), token)

    def test_logout_still_requires_csrf_and_clears_authentication(self):
        self.submit(form_token(self.client.get("/login")))
        token = form_token(self.client.get("/login"))
        self.post.reset_mock()
        user = {"email": ACCOUNT["email"], "workspaces": []}
        with patch.object(main.api, "get", AsyncMock(return_value=user)):
            rejected = self.client.post("/logout", data={"csrf_token": "wrong"}, follow_redirects=False)
            self.assertEqual(rejected.status_code, 403)
            self.post.assert_not_called()
            accepted = self.client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
        self.assertEqual(accepted.status_code, 303)
        self.post.assert_awaited_once_with("/api/auth/logout")
        self.assertIsNone(self.client.cookies.get(COOKIE))
        with patch.object(main.api, "get", AsyncMock()) as get:
            response = self.client.get("/dashboard", follow_redirects=False)
            self.assertEqual(response.headers["location"], "/login")
            get.assert_not_called()

    def test_unknown_notice_is_not_rendered(self):
        response = self.client.get("/login?notice=untrusted-notice")
        self.assertNotIn("untrusted-notice", response.text)


class SessionRaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_delayed_static_response_cannot_replace_a_new_login_session(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def delayed_app(scope, receive, send):
            async def delayed_send(message):
                if scope.get("path") == "/static/theme.js" and message["type"] == "http.response.start":
                    started.set()
                    await release.wait()
                await send(message)
            await main.app(scope, receive, delayed_send)

        post = AsyncMock(return_value={"token": "synthetic-account-token"})
        with patch.object(main.api, "post", post):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=delayed_app), base_url="https://dashboard.example.test") as browser:
                page = await browser.get("/login")
                old_token = form_token(page)
                pending = asyncio.create_task(browser.get("/static/theme.js"))
                try:
                    await asyncio.wait_for(started.wait(), timeout=5)
                    login = await browser.post("/login", data={**ACCOUNT, "csrf_token": old_token})
                    self.assertEqual(login.headers["location"], "/dashboard")
                    fresh = await browser.get("/login")
                    new_token = form_token(fresh)
                    self.assertNotEqual(old_token, new_token)
                finally:
                    release.set()
                    await pending
                # The older static request finishes after the new form/session.
                # It must not restore the previous anonymous cookie/CSRF token.
                retry = await browser.post("/login", data={**ACCOUNT, "csrf_token": new_token})
                self.assertEqual(retry.headers["location"], "/dashboard")
                self.assertEqual(post.await_count, 2)


if __name__ == "__main__":
    unittest.main()
