# Company research and automatic industry

For administrator-activated products, [shared product automation](../product/simple-product-onboarding.md) supersedes the manual acceptance/contact/qualification steps described below. Existing unactivated workspaces retain the reviewed workflow. Both modes stop before sending.

Updated: 6 October 2026.

Accepting a candidate creates one pending research job. The published DEV worker polls each minute, loads workspace context, recovers stale jobs and claims the next job with a per-workspace running limit of one. Empty queues make no search, fetch or model requests.

The research child validates the claimed lead, company, ICP and accepted candidate against that workspace. It performs company and leadership searches, plus an affiliation query for a known primary contact when present. It retrieves up to six guarded public pages and supplies at most ten sources and 24,000 evidence characters to xKiro. Person-profile lookup follows supported named-contact extraction.

Findings contain concise titles, category, observed/hypothesized status, exact supporting quote, source URLs and confidence. Public business contacts require literal name/role and company-affiliation evidence. Email or phone attribution is never guessed. Complete research needs verified official company evidence, supported services and sufficient overall confidence. Otherwise the report may be partial or failed.

The brief shows an executive summary, grouped findings, public contacts/profiles, research gaps, source library and earlier runs. Company and Primary Contact overview cards appear above it. A new pending/failed run does not hide an earlier useful brief. **Run research again** queues a fresh run for an existing lead.

## Industry promotion

The model may return `industry_classification` with a short label, confidence, exact quote and source URLs. Runtime validation requires official company evidence and confidence of at least 75. On completed research, the API independently checks the cited URLs and quote against sources saved on that same run, requires verified company identity, and fills the company's missing industry. Existing industry values are preserved. Attribution is retained in company metadata with a `company_industry_determined` audit event.

Older reports remain compatible but do not retroactively classify an empty field. After the updated API is deployed, rerun research on existing leads to populate industry. Insufficient evidence should remain unknown rather than produce a guessed label. Fleet estimates are a separate company field; this industry fix does not automatically promote fleet facts into it.

## Operations

Research uses the named workspace API credential, Brave Header Auth and the existing xKiro Header Auth credential. The xKiro key belongs in n8n credentials, not an API environment variable or Code node. Worker/child execution limits are 840/780 seconds; stale-running recovery marks jobs older than 30 minutes failed and preserves history.

Research does not create official Contact records, qualify the lead, run product matching or send messages. Those are subsequent stages with their own review and authorization rules.

Sources: [workflow generator](../../integrations/n8n/research-workflows.js), [runtime validators](../../integrations/n8n/research-runtime.js), [research service](../../api/app/services/research_service.py), [brief presentation guide](../../docs/research-brief.md), [people and industry implementation notes](../../docs/people-profile-search.md).


MVP1 contact coverage: bounded second-pass research now follows official management/leadership/board and contact links inside the existing total page limit. Navigation boilerplate is removed before evidence extraction. This fixes the observed Kontena Nasional case where search results omitted the visible Management Team page. 68 JavaScript regressions pass; live rerun queued, outcome pending.
