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


### Company discovery DEV acceptance — 11 October 2026

Code `8b9d162dfdcc6301404bbbe0060399703a9f213b` passed full push CI `38145984359` and PR CI `38145987247`. DEV deployment [38146226265](https://github.com/geekedctrl/lorrysystem-deploy/actions/runs/38146226265) succeeded. Discovery and setup child workflows were published through the DEV n8n API with existing named credentials and workspace/lease headers preserved; the dispatcher resumed. All three workflows are active with current published versions and execution saving set to `none`.

A normal public-HTTPS admin login and LorrySystem workspace switch submitted the unchanged dashboard default query with a target of one company. Discovery job `960988f3-ffcb-4835-80e3-4084f9b2d07c` completed with `COMPANIES_ACCEPTED`, one new candidate and one accepted lead: **Hock Cheong**, `hockcheong.com.my`, lead `53f3592e-b375-4f7b-bb49-5c46be4d78d2`. A separate normal HTTP session verified the company in `/leads`, its detail page and `/discovered-leads?status=ALL`. Both test sessions logged out. The batch used one search, two fetches and one model call (4,932 input / 137 output tokens); recorded monetary cost is unavailable.

Follow-up research automatically ran and stopped at `NEEDS_REVIEW` / `SUPPORTED_CONTACT_REQUIRED`; discovery succeeded, but outreach preparation is not claimed complete. No outreach was approved or sent. The task-created retained diagnostic execution `21159` and temporary credential-bearing verifiers/raw diagnostic payload were removed after verification. User-owned compose/gitignore contents remain intact. PR [34](https://github.com/geekedctrl/lorrysystem-marketing-system/pull/34) targets `develop` and includes unmerged PR33's session repair to preserve the DEV baseline. Production and native-worker rollout are unchanged.
