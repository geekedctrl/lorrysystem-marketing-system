"""Synthetic, offline tests for the mock strategy safety boundary."""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('POSTGRES_DB', 'synthetic')
os.environ.setdefault('POSTGRES_USER', 'synthetic')
os.environ.setdefault('POSTGRES_PASSWORD', 'synthetic')

from fastapi import HTTPException
from app.services.campaign_strategist import check_context, mock_strategy, require_editor, validate_strategy
from app.auth import check_business_permission
from app.schemas.campaign import Strategy, GenerateProposal
from app.workspace_context import Principal
from starlette.requests import Request


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.product = NS(id=uuid4(), name='Synthetic fleet tool', active=True, description=None)
        self.sources = [NS(id=uuid4(), evidence='Synthetic company operates a fleet.', url='https://example.test/fleet')]
        self.lead = NS(status='QUALIFIED', current_score=75)
        self.research = NS(research_status='COMPLETED', completed_at=self.now, researched_at=None)

    def test_synthetic_success_and_no_paid_generation(self):
        check_context(self.lead, self.research, self.sources, self.product, self.now)
        payload = validate_strategy(mock_strategy(self.sources, self.product), self.sources, self.product)
        self.assertEqual(payload['claims'][0]['source_ids'], [str(self.sources[0].id)])
        self.assertTrue(payload['hypotheses'])
        self.assertEqual(payload['assets'], [])
        self.assertEqual(payload['channels'], [])
        self.assertNotIn('send', payload)

    def test_malformed_or_extra_model_output_rejected(self):
        payload = mock_strategy(self.sources, self.product)
        payload['approve'] = True
        with self.assertRaises(HTTPException) as failure:
            validate_strategy(payload, self.sources, self.product)
        self.assertEqual(failure.exception.status_code, 422)

    def test_fabricated_claim_and_unknown_citation_rejected(self):
        payload = mock_strategy(self.sources, self.product)
        payload['claims'][0]['text'] = 'The company urgently needs our product.'
        with self.assertRaises(HTTPException):
            validate_strategy(payload, self.sources, self.product)
        payload = mock_strategy(self.sources, self.product)
        payload['claims'][0]['source_ids'] = [str(uuid4())]
        with self.assertRaises(HTTPException):
            validate_strategy(payload, self.sources, self.product)

    def test_stale_incomplete_and_future_research_rejected(self):
        for completed in [self.now - timedelta(days=31), self.now + timedelta(minutes=1), None]:
            self.research.completed_at = completed
            with self.assertRaises(HTTPException):
                check_context(self.lead, self.research, self.sources, self.product, self.now)
        self.research.completed_at = self.now
        self.research.research_status = 'PARTIAL'
        with self.assertRaises(HTTPException):
            check_context(self.lead, self.research, self.sources, self.product, self.now)

    def test_low_score_unqualified_missing_evidence_or_product_rejected(self):
        self.lead.current_score = 59
        with self.assertRaises(HTTPException):
            check_context(self.lead, self.research, self.sources, self.product, self.now)
        self.lead.current_score = 75
        with self.assertRaises(HTTPException):
            check_context(self.lead, self.research, [], self.product, self.now)
        with self.assertRaises(HTTPException):
            check_context(self.lead, self.research, self.sources, None, self.now)

    def test_budget_denies_spend_and_invalid_budget(self):
        payload = mock_strategy(self.sources, self.product)
        payload['assets'] = [{'type': 'POSTER', 'rationale': 'Synthetic', 'estimated_cost_usd': 1}]
        with self.assertRaises(HTTPException):
            validate_strategy(payload, self.sources, self.product, 50)
        with self.assertRaises(ValueError):
            GenerateProposal(idempotency_key=uuid4(), max_estimated_cost_usd=-1)

    def test_cross_catalog_product_rejected(self):
        payload = mock_strategy(self.sources, self.product)
        payload['product_id'] = str(uuid4())
        with self.assertRaises(HTTPException):
            validate_strategy(payload, self.sources, self.product)

    def test_services_and_viewers_cannot_generate_or_review(self):
        for role in ['SERVICE', 'VIEWER']:
            principal = Principal(uuid4(), 'synthetic', role, None if role == 'SERVICE' else uuid4())
            with self.assertRaises(HTTPException):
                require_editor(NS(info={'principal': principal}))
            for path in ['/api/leads/lead/campaign-proposals', '/api/campaign-proposals/proposal/review']:
                request = Request({'type': 'http', 'headers': [], 'method': 'POST', 'path': path})
                with self.assertRaises(HTTPException):
                    check_business_permission(principal, request)

    def test_operator_cannot_review_reviewer_can(self):
        request = Request({'type': 'http', 'headers': [], 'method': 'POST', 'path': '/api/campaign-proposals/proposal/review'})
        with self.assertRaises(HTTPException):
            check_business_permission(Principal(uuid4(), 'operator', 'OPERATOR', uuid4()), request)
        check_business_permission(Principal(uuid4(), 'reviewer', 'REVIEWER', uuid4()), request)

    def test_email_requires_fresh_sourced_active_contact(self):
        contact = NS(status='ACTIVE', source_url=self.sources[0].url, updated_at=self.now,
                     email='synthetic@example.test', linkedin_url=None)
        self.assertEqual(mock_strategy(self.sources, self.product, contact=contact, now=self.now)['channels'], [])
        self.sources[0].evidence += ' Public contact: synthetic@example.test'
        payload = mock_strategy(self.sources, self.product, contact=contact, now=self.now)
        self.assertEqual([c['channel'] for c in payload['channels']], ['EMAIL'])
        for change in [{'updated_at': self.now - timedelta(days=31)}, {'source_url': 'https://example.test/uncited'}, {'status': 'INACTIVE'}]:
            bad = NS(**{**vars(contact), **change})
            self.assertEqual(mock_strategy(self.sources, self.product, contact=bad, now=self.now)['channels'], [])

    def test_social_presence_and_asset_selection_are_conditional(self):
        self.sources[0].url = 'https://www.instagram.com/synthetic'
        self.product.description = 'Synthetic catalogue description with product details. ' * 3
        match = NS(fit_score=80)
        payload = validate_strategy(mock_strategy(self.sources, self.product, match=match), self.sources, self.product)
        self.assertEqual([c['channel'] for c in payload['channels']], ['INSTAGRAM'])
        self.assertEqual({a['type'] for a in payload['assets']}, {'BROCHURE', 'POSTER'})
        self.assertTrue(all(a['estimated_cost_usd'] is None and a['cost_rationale'] for a in payload['assets']))
        self.sources[0].url = 'https://instagram.com.attacker.test/synthetic'
        payload = mock_strategy(self.sources, self.product, match=NS(fit_score=50))
        self.assertEqual(payload['channels'], [])
        self.assertEqual(payload['assets'], [])

    def test_linkedin_draft_requires_current_contact_source(self):
        contact = NS(status='ACTIVE', source_url=self.sources[0].url, updated_at=self.now,
                     email=None, linkedin_url='https://www.linkedin.com/in/synthetic')
        self.assertEqual(mock_strategy(self.sources, self.product, contact=contact, now=self.now)['channels'], [])
        self.sources[0].evidence += ' Profile: https://www.linkedin.com/in/synthetic'
        self.assertEqual([c['channel'] for c in mock_strategy(self.sources, self.product, contact=contact, now=self.now)['channels']], ['LINKEDIN'])

    def test_edit_cannot_add_unsupported_engagement_channel(self):
        payload = mock_strategy(self.sources, self.product)
        payload['channels'] = [{'channel': 'EMAIL', 'subject': None, 'body': 'Synthetic draft', 'rationale': 'Synthetic recommendation'}]
        with self.assertRaises(HTTPException) as failure:
            validate_strategy(payload, self.sources, self.product)
        self.assertEqual(failure.exception.status_code, 422)


if __name__ == '__main__':
    unittest.main()

