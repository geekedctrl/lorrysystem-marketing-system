# Company-linked people and professional profiles

Updated: 6 October 2026.

Profile search runs after company research has supported a named person's relationship to the company. A saved primary contact is a search hint, not evidence by itself. When company evidence yields no supported named person, the workflow does not invent one.

Up to five supported people get two Brave queries each: LinkedIn individual profiles and professional social presence. The implementation supports LinkedIn, X/Twitter, Instagram and GitHub. It uses public indexed evidence and named outgoing links on official company pages; it does not log into social platforms or scrape their profile pages.

| State | Meaning |
| --- | --- |
| Matched | Public search evidence contains the full name and company. Social handles additionally require the researched job title; an official company link explicitly labelled with the person's name can also support a match. |
| Needs review | Several distinct profiles on one platform satisfy those checks. They remain separate candidates; no LinkedIn identity is picked automatically. |
| Not found | No profile meets the evidence checks. A similar name, generic company page or social footer is insufficient. |
| Search unavailable | Provider requests failed. Company research is retained; a fresh research run retries the search. |

A match is public evidence of association, not definitive identity or current-employment verification. Literal normalized name/company checks deliberately avoid inferring nicknames, acronyms or transliterations. Some legitimate profiles will therefore remain unfound.

Results are stored in each research person's `professional_profiles`, `profile_candidates` and `profile_search_status`. `company_facts.people_search` records bounded query counts, outages and completion time. Only an unambiguous matched LinkedIn profile fills `linkedin_url`. Supporting sources are saved with the report.

Review evidence and resolve conflicting identities before choosing a contact for outreach. Research does not promote people into official Contacts automatically. Broader social discovery of new companies remains a separate future feature.

Implementation: [profile runtime](../../integrations/n8n/people-runtime.js), [profile guide](../../docs/people-profile-search.md), [research presenter](../../dashboard/app/research_presenter.py).
