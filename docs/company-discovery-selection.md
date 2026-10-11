# Company discovery selection repair

## Observed DEV issue

On 11 October 2026, LorrySystem job `74fa1cb1-4b84-4514-9c6b-e51ccc9a440d` completed with zero accepted companies, as did two earlier batches with the same default query. Worker heartbeats and provider usage showed successful execution: one search, ten fetch attempts and one model response containing an empty candidate array. This was not a stopped dispatcher or login failure.

The default search (`Malaysian logistics and transport companies with fleet management needs`) returned mostly directories, rankings, previously accepted Quanterm and software articles. Selection spent its ten-page budget on the earlier results, before reaching a new operator's official homepage. Repeating the unchanged query repeated this unsuitable pool.

## Changes

Shared discovery now supplements the product/user query with official-company wording and bounded `-site:` exclusions from that workspace's existing company memory. Memory is retained; accepted companies remain excluded locally even if their domain cannot fit the search query. Only valid domain strings may become operators. Query generation is limited to 400 characters and 50 words, conservatively below the current [Brave web-search limits](https://api-dashboard.search.brave.com/api-reference/web/search/get); [search operators](https://api-dashboard.search.brave.com/documentation/resources/search-operators) are supported in the query parameter.

Known business directories and explicit ranking/listing pages are removed before allocating the fetch budget. Company homepages rank ahead of deep articles while preserving relative search rank within each group. Existing public-URL checks, per-domain deduplication, workspace/lease checks, fetched-source quotation checks and ICP confidence gates remain in force. No company is accepted from a directory snippet. Fetches remain bounded to at most twice the requested company target, capped at ten; a target is a maximum, not a guaranteed number of leads.

If all selected websites fail to provide evidence, discovery returns `DISCOVERY_FETCH_FAILED` rather than a successful no-match result. Empty assessments with usable evidence remain legitimate no-match outcomes. Product setup instructions now ask for customer business types and observable services instead of hypothetical buying needs or vendors of the catalog product.

The dashboard explains no-match/fetch/search/evidence outcomes. Managed discovery polling opens All discoveries when the run finishes, so automatically accepted companies are visible; completion and empty-state links lead to the official Leads list. Human outreach approval and separate sending are unchanged.

## Verification and release

All 76 n8n JavaScript tests pass, including directory-budget starvation, homepage priority, workspace-specific bounded query exclusions, unsafe-operator rejection and all-fetch failure. Thirteen login/session, eight campaign dashboard and five UX tests pass; discovery JavaScript syntax is valid. Two bounded diagnostic Brave searches verified the original directory-heavy pool and the revised official-company pool; real payloads remain private ignored files.

The DEV n8n child must be published separately from the app deployment. Its existing named credentials and lease headers must be preserved, along with the dispatcher and other child workflows. Changes are limited to discovery code/search preparation and the setup prompt. Live dashboard acceptance and release identifiers are recorded in `docs/ai/TEST_STATUS.md` and the PR. No production changes or outbound messages are part of this repair. Large-catalog search paging and broader calibration remain separate native-worker rollout work.
