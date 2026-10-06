# People and professional profiles

Company research now searches for public professional profiles after validating named people's connection to the company. The accepted-lead queue and workspace guards remain the entry point. No new API credential or database migration is required.

## Using it

Accept a discovered company to start research automatically. For a lead with an existing brief, choose **Run research again**. Profiles appear under **People & professional profiles**, with the public evidence used for the match. Previous briefs are preserved while a new run is pending.

If you already know a contact, assign them as the lead's primary contact and rerun research. Their name gets an additional company-affiliation search. The saved contact is a search hint: public evidence must still establish their name, role and company relationship before the profile search runs. No person is fabricated when company sources do not identify one.

LinkedIn searches use publicly indexed individual profiles. Professional social searches currently support X/Twitter, Instagram and GitHub. The workflow does not log into these platforms or fetch their profile pages. Company sites may also supply an outgoing professional link explicitly labelled with the person's name.

## Evidence and match states

- **Matched:** public search evidence contains the person's full name and the company name. Social handles additionally require the researched job title. An official company link labelled with the person's name can also support a match. This establishes a public evidence match, not definitive identity or current employment verification.
- **Needs review:** multiple distinct profiles on the same platform meet those checks. All are shown separately for inspection; no LinkedIn identity is selected automatically.
- **Not found:** searches returned no supported profile. A similar name, another company, company-page URL or generic social footer is insufficient.
- **Search unavailable:** provider requests failed. The company brief still completes and records the unavailable-query count; rerunning research retries the search.

Matching uses literal normalized names and company names with legal suffixes removed. It deliberately does not infer nicknames, company acronyms or transliterated names. Some valid profiles will therefore remain unfound. Users should review matched and possible profiles before selecting a contact for outreach. Research does not create official contact records, qualify leads or send messages.

## Runtime and persistence

`research-workflows.js` generates the new child graph. It uses the workspace's existing Brave Header Auth credential and keeps xKiro in the n8n credential store. Limits are five supported people, two queries each and five results per query. No extra model call is needed for profile matching. A known primary contact adds at most one initial company-research query. Worker/child execution timeouts are 840/780 seconds.

Each person's `company_facts.people` entry now includes `professional_profiles`, `profile_candidates` and `profile_search_status`. Profile entries carry platform, handle, URL, match basis, evidence quote, source URLs and evidence confidence. `linkedin_url` contains only an unambiguous matched LinkedIn profile. `company_facts.people_search` records bounded query counts, unavailable queries and completion time. Supporting evidence is saved through the existing workspace-scoped research sources endpoint before completing the report.

The dashboard displays matched profiles and conflicting candidates separately, with evidence expansion and stable source citations. Existing reports remain readable and show that profile search has not yet run.

## Validation

Run the JS suite including `integrations/n8n/people.test.js`, and `python dashboard/scripts/validate_research_presentation.py`. CI also runs the existing disposable API/dashboard workspace checks. The native n8n graph was exercised locally with mocked provider responses and the real disposable API in two workspaces, including source persistence, profile fields, empty queues, partial company evidence, model failures and workspace mismatch. Desktop and mobile dashboard checks use fictional preview contacts.

For DEV publishing, regenerate the child with its existing workspace binding, preserve its workflow ID and credential references, and publish it. Update only the parent's execution timeout to 840 seconds. After the dashboard PR is merged and deployed by CI/CD, rerun research on an existing lead to populate profiles. Later qualification, product matching and outreach remain separate stages.

## Company overview and industry

The Company and Primary Contact overview now precedes the research brief. An unnamed contact displays Name not identified. Completed research fills a missing company industry from a structured `industry_classification` with a concise label, confidence of at least 75, an exact quote and source URLs. The API checks the quote against official company evidence saved on that same research run and requires verified company identity. It preserves existing industry values and retains attribution in company metadata and an audit event. No database migration is required. Existing leads need Run research again after the API/dashboard deployment to populate a missing industry; older unstructured reports remain compatible.
