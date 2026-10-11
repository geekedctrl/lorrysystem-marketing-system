# Company discovery selection repair

## Observed DEV issue

On 11 October 2026, LorrySystem job `74fa1cb1-4b84-4514-9c6b-e51ccc9a440d` completed with zero accepted companies, as did two earlier batches with the same default query. Worker heartbeats and provider usage showed successful execution: one search, ten fetch attempts and one model response containing an empty candidate array. This was not a stopped dispatcher or login failure.

The default search (`Malaysian logistics and transport companies with fleet management needs`) returned mostly directories, rankings, previously accepted Quanterm and software articles. Selection spent its ten-page budget on the earlier results, before reaching a new operator's official homepage. Repeating the unchanged query repeated this unsuitable pool.

## Changes

Shared discovery now supplements the product/user query with official-company wording and bounded `-site:` exclusions from that workspace's existing company memory. Memory is retained; accepted companies remain excluded locally even if their domain cannot fit the search query. Only valid domain strings may become operators. Query generation is limited to 400 characters and 50 words, conservatively below the current [Brave web-search limits](https://api-dashboard.search.brave.com/api-reference/web/search/get); [search operators](https://api-dashboard.search.brave.com/documentation/resources/search-operators) are supported in the query parameter.

Known business directories and explicit ranking/listing pages are removed before allocating the fetch budget. Company homepages rank ahead of deep articles while preserving relative search rank within each group. Existing public-URL checks, per-domain deduplication, workspace/lease checks, fetched-source quotation checks and ICP confidence gates remain in force. No company is accepted from a directory snippet. Fetches remain bounded to at most twice the requested company target, capped at ten; a target is a maximum, not a guaranteed number of leads.

If all selected websites fail to provide evidence, discovery returns `DISCOVERY_FETCH_FAILED` rather than a successful no-match result. Empty assessments with usable evidence remain legitimate no-match outcomes. Product setup instructions now ask for customer business types and observable services instead of hypothetical buying needs or vendors of the catalog product.

The dashboard explains no-match/fetch/search/evidence outcomes. Managed discovery polling opens All discoveries when the run finishes, so automatically accepted companies are visible; completion and empty-state links lead to the official Leads list. Human outreach approval and separate sending are unchanged.

## Source excerpt selection

The first corrected-search live batch still failed evidence validation. A bounded diagnostic batch confirmed that the model combined nonadjacent passages from Hock Cheong's official website into one quote, omitting intervening headings and mission/vision text. The recorded quote was rejected correctly. Prompt instructions alone had not prevented this repeated error.

The model now selects `source_id` and `excerpt_id` from overlapping windows of fetched text, rather than generating a URL and quote. Source URLs and saved quotations are resolved deterministically from those identifiers. Each page supplies at most eight excerpts of at most 1,000 characters from at most 6,000 fetched characters. Unknown or cross-page identifiers, unsupported company names, foreign/prototype ICP keys, unverified identity and low confidence remain rejected. Legacy output with an explicit quote remains supported only when its original strict continuous-quotation checks pass. Model-written replacements cannot alter the selected fetched excerpt or source URL.

## Verification and release

All 79 n8n JavaScript tests pass, including directory-budget starvation, homepage priority, workspace-specific bounded query exclusions, unsafe-operator rejection, all-fetch failure and exact source-identifier quotation persistence/rejection. Thirteen login/session, eight campaign dashboard and five UX tests pass; discovery JavaScript syntax is valid. Two bounded diagnostic Brave searches verified the original directory-heavy pool and the revised official-company pool; real payloads remain private ignored files. Execution retention was temporarily enabled for one diagnostic discovery batch and restored to `none` immediately after collection.

The DEV n8n child must be published separately from the app deployment. Its existing named credentials and lease headers must be preserved, along with the dispatcher and other child workflows. Changes are limited to discovery code/search preparation and the setup prompt. Live dashboard acceptance and release identifiers are recorded in `docs/ai/TEST_STATUS.md` and the PR. No production changes or outbound messages are part of this repair. Large-catalog search paging and broader calibration remain separate native-worker rollout work.
