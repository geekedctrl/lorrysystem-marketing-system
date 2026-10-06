"""Evidence references, history selection and legacy research presentation regression."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.research_presenter import present_report, research_view, safe_research_url, present_scores


def report(identifier='old', created='2026-10-05T12:00:00Z', status='COMPLETED'):
    return {'id': identifier, 'created_at': created, 'research_status': status, 'summary': 'A useful company overview.',
        'confidence': 85, 'sources': [{'url': 'https://acme.com', 'title': 'Acme company', 'evidence': 'Public source evidence.'},
            {'url': 'https://acme.com/services', 'title': 'Acme services'}],
        'company_facts': {'facts': [
            {'category': 'COMPANY', 'fact': 'Established logistics company.', 'source_urls': ['https://acme.com/']},
            {'category': 'SERVICES', 'title': 'Core services', 'fact': 'Provides road haulage.', 'source_urls': ['https://acme.com/services', 'https://acme.com/']}],
            'people': [], 'coverage': {'official_pages_read': 2}}}


class ResearchPresentationTests(unittest.TestCase):
    def test_professional_profiles_keep_match_evidence_and_ambiguous_results_separate(self):
        item = report()
        matched = {'platform': 'LinkedIn', 'url': 'https://www.linkedin.com/in/jane', 'handle': 'jane',
            'match_status': 'MATCHED', 'match_basis': 'PUBLIC_NAME_COMPANY_MATCH',
            'evidence_quote': 'Jane Tan - Acme Logistics', 'source_urls': ['https://www.linkedin.com/in/jane']}
        candidate = {**matched, 'url': 'https://www.linkedin.com/in/jane-other', 'match_status': 'NEEDS_REVIEW'}
        item['company_facts']['people'] = [{'name': 'Jane Tan', 'profile_search_status': 'NEEDS_REVIEW',
            'professional_profiles': [matched, {**matched, 'url': 'https://evil.com/in/jane'}], 'profile_candidates': [candidate]}]
        person = present_report(item)['people'][0]
        self.assertEqual(len(person['profiles']), 1)
        self.assertEqual(len(person['profile_candidates']), 1)
        self.assertEqual(person['profiles'][0]['quote'], matched['evidence_quote'])
        self.assertEqual(person['profiles'][0]['citations'][0]['number'], 3)
        self.assertEqual(person['profile_status'], 'Conflicting profiles need review')

    def test_missing_profiles_and_search_outage_are_not_claimed_as_matches(self):
        for status, label in [('NOT_FOUND', 'No supported profile found'), ('SEARCH_UNAVAILABLE', 'Profile search temporarily unavailable')]:
            item = report(); item['company_facts']['people'] = [{'name': 'Jane Tan', 'profile_search_status': status, 'professional_profiles': []}]
            person = present_report(item)['people'][0]
            self.assertEqual(person['profile_status'], label)
            self.assertEqual(person['profiles'], [])

    def test_one_consistent_reference_number_for_each_source(self):
        brief = present_report(report())
        self.assertEqual(len(brief['sources']), 2)
        self.assertEqual([r['number'] for r in brief['sections'][1]['findings'][0]['citations']], [2, 1])
        self.assertEqual(brief['sections'][0]['findings'][0]['citations'][0]['number'], 1)
        self.assertEqual(brief['sections'][1]['findings'][0]['title'], 'Core services')

    def test_latest_failed_or_running_run_does_not_hide_the_useful_brief(self):
        for status in ('FAILED', 'PENDING', 'RUNNING'):
            latest = {'id': 'latest', 'created_at': '2026-10-06T12:00:00Z', 'research_status': status}
            view = research_view([report(), latest])
            self.assertEqual(view['report']['id'], 'old')
            self.assertEqual(view['latest']['status'], status)
            self.assertEqual(len(view['history']), 2)

    def test_history_selection_stays_within_current_lead_reports(self):
        old = report(); newer = report('new', '2026-10-06T12:00:00Z')
        self.assertTrue(research_view([newer, old], 'old')['viewing_history'])
        self.assertEqual(research_view([newer, old], 'foreign-id')['report']['id'], 'new')
        self.assertEqual(research_view([])['report'], None)

    def test_unsafe_links_and_malformed_old_facts_do_not_become_controls(self):
        for url in ('javascript:alert(1)', 'https://user:password@acme.com', 'https://acme.com/\nattack'):
            self.assertIsNone(safe_research_url(url))
        item = report(); item['company_facts'] = {'facts': [None, 'raw text', {'category': 'UNKNOWN', 'fact': 'Bad section'}],
            'people': [{'name': 'Jane Tan', 'business_email': 'jane@acme.com?subject=attack', 'linkedin_url': 'javascript:alert(1)'}]}
        brief = present_report(item)
        self.assertEqual(brief['sections'], [])
        self.assertIsNone(brief['people'][0]['email_href']); self.assertIsNone(brief['people'][0]['profile'])

    def test_structured_signals_are_not_repeated_and_legacy_reports_keep_theirs(self):
        item = report(); item['company_facts']['facts'].append({'category': 'SIGNAL', 'fact': 'New operating depot'})
        item['buying_signals'] = ['New operating depot']
        brief = present_report(item)
        self.assertEqual(sum(len(section['findings']) for section in brief['sections']), 3)
        item['company_facts'] = {}; item['pain_points'] = ['Possible dispatch coordination need']
        legacy = present_report(item)
        self.assertEqual(len(legacy['sections']), 2)
        self.assertEqual(legacy['sections'][1]['findings'][0]['inferred'], True)


class ScorePresentationTests(unittest.TestCase):
    def test_score_criteria_preserve_values_and_reject_executable_source_links(self):
        saved={'total_score':40,'score_breakdown':{'rubric':[{'criterion':'icp_fit','label':'ICP fit'}],
            'components':[{'criterion':'icp_fit','points':40,'max_points':40,'rationale':'Documented public fleet.',
                'evidence':[{'source_url':'javascript:alert(1)','evidence_quote':'Unsupported link'},
                            {'source_url':'https://acme.com/','evidence_quote':'Public fleet evidence'}]}],
            'gaps':['Buying intent unknown']}}
        view=present_scores([saved])[0]
        self.assertEqual(view['view_components'][0]['title'],'ICP fit')
        self.assertEqual(len(view['view_components'][0]['evidence']),1)
        self.assertEqual(view['view_gaps'],['Buying intent unknown'])
        self.assertEqual(present_scores([{'score_breakdown':{'components':None,'rubric':None}}])[0]['view_components'],[])
        self.assertNotIn('view_components',saved)


if __name__ == '__main__':
    unittest.main()
