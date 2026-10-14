import io
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from app.services.executor_ownership import legacy_claim_allowed, require_legacy_claim


class OwnershipPreflightTests(unittest.TestCase):
    def setUp(self):
        self.workspace = uuid4()
        self.environment = patch.dict(os.environ, {
            "OWNERSHIP_AUTHORITY_URL": "http://backend-api:8000",
            "OWNERSHIP_PREFLIGHT_TOKEN": "synthetic-secret",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_n8n_active_allows_new_claim(self):
        with patch("app.services.executor_ownership.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps({"allow_new_legacy_claim": True}).encode())):
            self.assertTrue(legacy_claim_allowed(self.workspace, "DISCOVERY"))

    def test_drain_stops_new_claim(self):
        with patch("app.services.executor_ownership.urllib.request.urlopen",
                   return_value=io.BytesIO(json.dumps({"allow_new_legacy_claim": False}).encode())):
            with self.assertRaises(HTTPException) as caught:
                require_legacy_claim(self.workspace, "PREPARATION")
        self.assertEqual(caught.exception.status_code, 409)

    def test_unreachable_authority_fails_closed(self):
        with patch("app.services.executor_ownership.urllib.request.urlopen", side_effect=OSError()):
            with self.assertRaises(HTTPException) as caught:
                require_legacy_claim(self.workspace, "SENDING")
        self.assertEqual(caught.exception.status_code, 503)

    def test_missing_configuration_fails_closed(self):
        with patch.dict(os.environ, {"OWNERSHIP_PREFLIGHT_TOKEN": ""}):
            with self.assertRaises(HTTPException) as caught:
                require_legacy_claim(self.workspace, "SETUP")
        self.assertEqual(caught.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
