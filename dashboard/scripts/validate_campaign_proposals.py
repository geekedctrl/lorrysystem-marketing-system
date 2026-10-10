"""Campaign dashboard regressions using synthetic data and mocked API calls."""
import os
import sys
import unittest
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch

root = Path(__file__).resolve().parents[1]
os.chdir(root)
os.environ['DASHBOARD_SESSION_SECRET'] = 'synthetic-dashboard-test-secret'
sys.path.insert(0, str(root))
from starlette.requests import Request
from app import main
from app import import_helpers
from app.api_client import MarketingAPIError


def request():
    return Request({'type': 'http', 'method': 'POST', 'path': '/', 'query_string': b'', 'headers': [], 'session': {'csrf_token': 'valid'}})


class CampaignDashboardTests(unittest.IsolatedAsyncioTestCase):
    def test_import_directory_uses_platform_temp_directory(self):
        self.assertEqual(import_helpers.IMPORT_DIR, Path(tempfile.gettempdir()) / 'lorrysystem-dashboard-imports')
        self.assertTrue(import_helpers.IMPORT_DIR.is_dir())
    async def test_csrf_blocks_every_mutation_before_api(self):
        with patch.object(main.api, 'post', AsyncMock()) as post, patch.object(main.api, 'patch', AsyncMock()) as update:
            await main.generate_campaign_proposal(request(), 'lead', 'bad', 'key')
            await main.edit_campaign_proposal(request(), 'proposal', 'bad', 1, '{}')
            await main.review_campaign_proposal(request(), 'proposal', 'bad', 1, 'REVIEWED', '')
            post.assert_not_called()
            update.assert_not_called()

    async def test_generation_forwards_retry_key_and_zero_budget(self):
        with patch.object(main.api, 'post', AsyncMock(return_value={'id': 'proposal'})) as post:
            result = await main.generate_campaign_proposal(request(), 'lead', 'valid', 'retry-key')
            self.assertEqual(result.headers['location'], '/campaign-proposals/proposal')
            post.assert_awaited_once_with('/api/leads/lead/campaign-proposals', json={'idempotency_key': 'retry-key', 'max_estimated_cost_usd': 0})

    async def test_edit_invalid_json_never_calls_api(self):
        with patch.object(main.api, 'patch', AsyncMock()) as update:
            result = await main.edit_campaign_proposal(request(), 'proposal', 'valid', 1, '[]')
            self.assertIn('error=', result.headers['location'])
            update.assert_not_called()

    async def test_stale_review_surfaces_api_conflict(self):
        with patch.object(main.api, 'post', AsyncMock(side_effect=MarketingAPIError(409, 'Reload current version'))):
            result = await main.review_campaign_proposal(request(), 'proposal', 'valid', 1, 'REJECTED', 'Unsupported strategy')
            self.assertIn('Reload%20current%20version', result.headers['location'])

    async def test_structured_edits_preserve_evidence_and_version(self):
        req = request()
        req.form = AsyncMock(return_value={'channel_0_subject': 'Updated', 'channel_0_body': 'Reviewed copy', 'channel_0_rationale': 'Evidence fit'})
        with patch.object(main.api, 'patch', AsyncMock()) as update:
            await main.edit_campaign_proposal(req, 'proposal', 'valid', 3, '{"claims":[{"text":"Evidence","source_ids":["source"]}],"channels":[{"channel":"EMAIL"}]}', 'New objective', 'New positioning')
            payload = update.await_args.kwargs['json']
            self.assertEqual(payload['expected_version'], 3)
            self.assertEqual(payload['strategy']['claims'][0]['source_ids'], ['source'])
            self.assertEqual(payload['strategy']['channels'][0]['body'], 'Reviewed copy')

    def test_template_escapes_copy_and_rejects_unsafe_evidence_url(self):
        main.templates.env.get_template('lead_detail.html')
        proposal = {'id': 'p', 'lead_id': 'l', 'research_id': 'r', 'status': 'DRAFT', 'version': 1, 'provider': 'mock', 'estimated_cost_usd': 0, 'actual_cost_usd': 0, 'strategy': {'objective': '<script>alert(1)</script>', 'positioning': 'Position', 'claims': [], 'hypotheses': [], 'channels': [], 'assets': [], 'warnings': []}}
        rendered = main.templates.env.get_template('campaign_proposal.html').render(request=request(), current_workspace={'name': 'Test', 'role': 'REVIEWER'}, proposal=proposal, research={'sources': [{'id': 's', 'url': 'javascript:alert(1)', 'title': 'Source'}]}, strategy_json='{}', csrf_token='valid')
        self.assertNotIn('<script>alert(1)</script>', rendered)
        self.assertNotIn('javascript:', rendered)
        self.assertIn('Mark strategy reviewed', rendered)
        self.assertNotIn('Send approved email', rendered)

    def test_unknown_asset_cost_is_not_shown_as_free(self):
        proposal = {'id': 'p', 'lead_id': 'l', 'research_id': 'r', 'status': 'DRAFT', 'version': 1, 'provider': 'mock', 'estimated_cost_usd': 0, 'actual_cost_usd': 0, 'strategy': {'objective': 'Objective', 'positioning': 'Position', 'claims': [], 'hypotheses': [], 'channels': [], 'assets': [{'type': 'POSTER', 'rationale': 'Recommended', 'estimated_cost_usd': None, 'cost_rationale': 'Provider pricing is unavailable.'}], 'warnings': []}}
        rendered = main.templates.env.get_template('campaign_proposal.html').render(request=request(), current_workspace={'name': 'Test', 'role': 'REVIEWER'}, proposal=proposal, research={'sources': []}, strategy_json='{}', csrf_token='valid')
        self.assertIn('Not priced', rendered)
        self.assertIn('Provider pricing is unavailable.', rendered)
        self.assertNotIn('Estimate USD None', rendered)


if __name__ == '__main__':
    unittest.main()
