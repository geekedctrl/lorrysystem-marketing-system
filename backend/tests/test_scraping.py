"""Scraper extraction and actual isolated Chromium network-boundary checks."""

import os
import unittest
from unittest.mock import patch
from marketing_backend.scraping import readable, render_public
from marketing_backend.public_fetch import fetch_public, FetchError


class ScrapingTests(unittest.TestCase):
    def test_main_company_text_excludes_script_noise(self):
        html = "<html><nav>Cookie settings</nav><main><h1>Example Logistics</h1><p>Example Logistics operates commercial transport, delivery and freight forwarding services across Malaysia.</p><p>Our company operates a logistics fleet and provides warehousing and distribution for business customers.</p></main><script>Unverified Company owns 9999 trucks</script></html>"
        text = readable(html)
        self.assertIn("Example Logistics", text)
        self.assertNotIn("9999", text)

    def test_browser_asset_redirect_cannot_escape_allowed_company(self):
        with patch("marketing_backend.public_fetch.robots_permission"), patch(
            "marketing_backend.public_fetch.request_once",
            return_value={
                "status": 302,
                "location": "https://other-public.com/asset.js",
            },
        ) as request:
            with self.assertRaises(FetchError) as caught:
                fetch_public(
                    "https://company.com/asset.js", allowed_hosts={"company.com"}
                )
            self.assertEqual(caught.exception.reason, "CROSS_SITE_REQUEST_DENIED")
            self.assertEqual(request.call_count, 1)

    @unittest.skipUnless(
        os.getenv("DISCOVERY_BROWSER_TEST") == "true",
        "Chromium installed in dedicated browser acceptance only",
    )
    def test_real_render_uses_guarded_assets_and_blocks_private_requests(self):
        calls = []
        html = """<html><main id="company">Loading</main><script src="/company.js"></script></html>"""
        script = """document.querySelector('#company').textContent='Example Logistics provides commercial transport and delivery services for business customers throughout Malaysia. Our logistics company provides warehousing, distribution and freight forwarding.'; fetch('http://127.0.0.1:9876/private').catch(()=>document.body.dataset.privateBlocked='yes');"""

        def guarded(url, **options):
            calls.append(url)
            self.assertEqual(options["allowed_hosts"], {"company.com"})
            self.assertTrue(url.startswith("https://company.com/"))
            return dict(
                fetch_status="SUCCESS",
                final_url=url,
                body=script if url.endswith(".js") else html,
                content_type=(
                    "application/javascript" if url.endswith(".js") else "text/html"
                ),
            )

        with patch("marketing_backend.scraping.fetch_public", side_effect=guarded):
            result = render_public("https://company.com/")
        self.assertIn("Example Logistics", readable(result))
        self.assertIn('data-private-blocked="yes"', result)
        self.assertEqual(
            calls, ["https://company.com/", "https://company.com/company.js"]
        )
