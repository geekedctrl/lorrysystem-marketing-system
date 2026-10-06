"""Present saved research as a readable brief without changing its evidence."""
import re
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit, urlunsplit


CATEGORIES = (
    ('COMPANY', 'Company background', 'Profile and business focus'),
    ('SERVICES', 'Services & operations', 'What the company delivers'),
    ('FLEET', 'Fleet & capacity', 'Equipment, scale and operating capacity'),
    ('TECHNOLOGY', 'Systems & infrastructure', 'Tools and infrastructure mentioned in public sources'),
    ('LOCATION', 'Locations & coverage', 'Where the company operates'),
    ('SIGNAL', 'Buying signals', 'Documented changes and business activity'),
    ('PAIN_POINT', 'Potential needs', 'Research hypotheses to validate in a conversation'),
)


def safe_research_url(value):
    if not isinstance(value, str) or any(ord(char) < 33 for char in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            return None
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or '/', parsed.query, ''))
    except ValueError:
        return None


def text(value):
    return value.strip() if isinstance(value, str) else ''


def strings(value):
    return [text(item) for item in value if text(item)] if isinstance(value, list) else []


def score(value):
    return value if type(value) is int and 0 <= value <= 100 else None


def report_date(value):
    try:
        date = datetime.fromisoformat(text(value).replace('Z', '+00:00'))
        return f'{date.day} {date:%b %Y}'
    except ValueError:
        return 'Date unavailable'


def report_time(value):
    try:
        date = datetime.fromisoformat(text(value).replace('Z', '+00:00'))
        date = date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date.astimezone(timezone.utc)
        return f'{date:%H:%M} UTC'
    except ValueError:
        return ''


def present_report(item):
    facts = item.get('company_facts')
    facts = facts if isinstance(facts, dict) else {}
    prefix = 'research-' + re.sub(r'[^a-zA-Z0-9_-]', '', text(item.get('id')))
    sources, by_url = [], {}

    def source(value):
        url = safe_research_url(value.get('url'))
        if not url:
            return None
        if url in by_url:
            existing = by_url[url]
            if not existing['evidence']:
                existing['evidence'] = text(value.get('evidence'))
            return existing
        number = len(sources) + 1
        entry = {'number': number, 'anchor': f'{prefix}-source-{number}', 'url': url,
                 'domain': urlsplit(url).hostname.removeprefix('www.'),
                 'title': text(value.get('title')) or urlsplit(url).hostname,
                 'evidence': text(value.get('evidence')), 'confidence': score(value.get('confidence'))}
        sources.append(entry); by_url[url] = entry
        return entry

    for value in item.get('sources') or []:
        if isinstance(value, dict):
            source(value)

    def citations(values):
        refs = []
        for url in strings(values):
            ref = source({'url': url})
            if ref and ref not in refs:
                refs.append(ref)
        return refs

    grouped = {category: [] for category, _, _ in CATEGORIES}
    for finding in facts.get('facts') if isinstance(facts.get('facts'), list) else []:
        if not isinstance(finding, dict) or finding.get('category') not in grouped or not text(finding.get('fact')):
            continue
        grouped[finding['category']].append({'title': text(finding.get('title')),
            'body': text(finding['fact']), 'quote': text(finding.get('evidence_quote')),
            'confidence': score(finding.get('confidence')), 'inferred': finding.get('evidence_status') == 'INFERRED',
            'citations': citations(finding.get('source_urls'))})
    # Older reports keep their useful signals without repeating structured findings.
    for category, field in (('SIGNAL', 'buying_signals'), ('PAIN_POINT', 'pain_points')):
        if not grouped[category]:
            for value in strings(item.get(field)):
                grouped[category].append({'title': '', 'body': value, 'quote': '', 'confidence': None,
                    'inferred': category == 'PAIN_POINT', 'citations': []})
    sections = [{'category': category, 'title': title, 'description': description, 'findings': grouped[category]}
                for category, title, description in CATEGORIES if grouped[category]]
    people = []
    for person in facts.get('people') if isinstance(facts.get('people'), list) else []:
        if not isinstance(person, dict) or not text(person.get('name')):
            continue
        name = text(person['name'])
        email = text(person.get('business_email'))
        phone = text(person.get('business_phone'))
        people.append({'name': name, 'initials': ''.join(part[0] for part in name.split()[:2]).upper(),
            'title': text(person.get('job_title')) or 'Role not specified',
            'role': text(person.get('role_classification')).replace('_', ' ').title(),
            'email': email, 'email_href': 'mailto:' + email if re.fullmatch(r'[^\s@?&#]+@[^\s@?&#]+\.[^\s@?&#]+', email) else None,
            'phone': phone, 'phone_href': 'tel:' + re.sub(r'[^+\d]', '', phone) if re.fullmatch(r'[+\d ().-]{7,60}', phone) else None,
            'profile': safe_research_url(person.get('linkedin_url')), 'quote': text(person.get('evidence_quote')),
            'confidence': score(person.get('confidence')), 'citations': citations(person.get('source_urls'))})
    coverage = facts.get('coverage') if isinstance(facts.get('coverage'), dict) else {}
    confidence = score(item.get('confidence'))
    status = text(item.get('research_status'))
    return {'id': text(item.get('id')), 'status': status, 'status_label': {'COMPLETED': 'Complete', 'PARTIAL': 'Partial',
        'PENDING': 'Queued', 'RUNNING': 'In progress', 'FAILED': 'Needs attention'}.get(status, 'Research'),
        'date': report_date(item.get('completed_at') or item.get('created_at')),
        'time': report_time(item.get('completed_at') or item.get('created_at')),
        'summary': [paragraph.strip() for paragraph in re.split(r'\n\s*\n', text(item.get('summary'))) if paragraph.strip()],
        'sections': sections, 'people': people, 'sources': sources, 'gaps': strings(facts.get('missing_information')),
        'confidence': confidence, 'confidence_label': 'Not assessed' if confidence is None else 'High' if confidence >= 80 else 'Moderate' if confidence >= 60 else 'Limited',
        'official_pages': coverage.get('official_pages_read') if type(coverage.get('official_pages_read')) is int else None,
        'finding_count': sum(len(section['findings']) for section in sections),
        'href': '?research_run=' + quote(text(item.get('id')), safe='') + '#research-brief'}


def research_view(items, requested_run=None):
    ordered = sorted(items, key=lambda item: text(item.get('created_at')), reverse=True)
    reports = [present_report(item) for item in ordered]
    selected = next((report for report in reports if report['id'] == requested_run), None)
    useful = next((report for report in reports if report['status'] in ('COMPLETED', 'PARTIAL')
                   and (report['summary'] or report['sections'] or report['people'])), None)
    selected = selected or useful or (reports[0] if reports else None)
    active = next((report for report in reports if report['status'] == 'RUNNING'), None)
    active = active or next((report for report in reports if report['status'] == 'PENDING'), None)
    return {'report': selected, 'history': reports, 'latest': reports[0] if reports else None,
            'active': active,
            'viewing_history': bool(requested_run and selected and selected['id'] == requested_run and reports[0]['id'] != selected['id'])}
