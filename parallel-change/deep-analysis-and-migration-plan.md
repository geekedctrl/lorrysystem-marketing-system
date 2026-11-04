# Parallel AI takeover: project analysis and migration plan

Status: research and planning; no implementation, paid provider calls, deployment, or outbound actions are authorized by this document. Based on the current working tree on 4 November 2026. Existing uncommitted changes and staged deletions must be preserved.

## Product direction

Parallel becomes the sole active provider for web intelligence: company discovery, official website identification, independent supporting sources, company research, and public business contact discovery. Brave and xKiro are removed from these web-intelligence paths after replacement is verified. Product-specific qualification, matching, drafting, workspace isolation, candidate review, and outreach approval remain application-owned. The model provider for scoring, matching and content generation is a separate decision; xKiro may remain there until replaced.

Parallel's AI should be the primary entity resolver: ask it to identify the company, propose its official website, and return supporting sources. The application validates structure, public URL safety, duplicate identities, workspace boundaries, and usable source evidence; it presents the proposed relationship for human review. Parallel results remain fallible and must not automatically create accepted leads. Evaluate its entity-resolution capabilities and actual API contracts before choosing the product and processor.

This is a direct provider replacement, not a permanent dual-provider or A/B architecture. Preserve previous code/configuration in version control and maintain a documented rollback, but do not automatically fall back to Brave or trigger additional provider spend.

## Monthly budget

The user's budget is **$32 per month in Parallel API credits**. DigitalOcean hosting costs a separate $12 per month; together these are $44 per month before other charges. The plan must fit within the Parallel credits and must not assume that an exhausted credit balance prevents paid overage. Confirm the provider's billing cycle, credit applicability, rollover, taxes and any overage settings; enforce a conservative fail-closed Parallel usage limit in the application before live use. Other paid services and overages are additional and require separate authorization. Synthetic tests and any live evaluation follow the separate approval gates below.

## Current system: what exists

1. **Runtime and ownership.** `backend/marketing_backend/runner.py`, `worker.py`, `queue.py`, and `pools.py` implement separate stage pools, PostgreSQL claims, leases, heartbeats, checkpoints and retries. The scheduler is responsible for lease recovery. The current local stack has historically run only selected pools; service health must be checked at rollout. `compose.worker-pools.yml` defines DISCOVERY, RESEARCH, CONTACT_SEARCH, SCORING, MATCHING, DRAFTING, delivery and scheduler pools.
2. **Provider boundary and budget.** `backend/marketing_backend/providers.py` implements Brave search, xKiro model calls, cache/checkpoint integration and provider reservations. `ProviderUsage` and per-line/global budget logic track attempts and estimated costs. Research, contacts, discovery, scoring, matching and drafting share this class, so deleting xKiro wholesale would break non-web stages. Existing price settings may not represent actual bills (current model prices were configured as zero); reconcile them before claiming a complete monthly cap.
3. **Discovery.** `backend/marketing_backend/discovery.py` builds ICP-specific queries, filters and ranks results, uses guarded fetch/extraction, asks the model for structured assessments and validates excerpts. It limits ordinary search and page counts, and tracks evaluated and filtered domains. `domain_corroboration.py` adds conservative first-party/registry checks; it requires matching text in a narrow clause and can classify legitimate sites UNCERTAIN. This is a screening heuristic, not proof of ownership.
4. **Persistence and manual decision.** `pipeline.py` stores `DiscoveryMemory` outcomes; `discovery_api.py` lists, accepts, rejects, retries, and performs targeted official-site searches. Acceptance checks workspace/role, source and corroboration before atomically creating a lead and preparation job. `reassessment.py` handles selected terminal reassessment outcomes. Do not turn a Parallel result into an accepted lead automatically.
5. **Research and contacts.** `stages.py` research consumes fetched pages, validates model-generated facts and citations, and may stop for missing evidence. Contact search finds public business contacts and stops for human review when identity or evidence is ambiguous. These outputs are consumed by qualification and matching; inspect actual schemas and call sites when implementing rather than assuming vendor output is a drop-in replacement.
6. **Contracts and UI.** `stage_contracts.py` and `worker_contracts.py` enforce versioned stage artifacts, including discovery candidate v3. Migration `018_discovery_candidate_v3.py` allows v3 artifacts; old versions remain relevant for in-flight work and history. `contracts.py`, `frontend_api.py`, `dashboard/app/native.py`, and `dashboard/app/static/native.js` expose and render candidate evidence, jobs, reassessments and review controls.
7. **Delivery.** Scoring/matching and drafting lead to a pending approval. Email/social/messaging pools and sender credentials have their own authorization, outbox and uncertain-delivery handling. Parallel integration must not bypass or trigger sending.

## Parallel product and URLs

- Platform/account: https://platform.parallel.ai/home (sign-in required; account plan and limits not inspected).
- Documentation index: https://docs.parallel.ai/home and https://docs.parallel.ai/llms.txt.
- Search: https://docs.parallel.ai/search/search-quickstart ; REST API `POST https://api.parallel.ai/v1/search`.
- Extract: https://docs.parallel.ai/extract/extract-quickstart ; REST API `POST https://api.parallel.ai/v1/extract`.
- Task research/enrichment: https://docs.parallel.ai/integrations/mcp/task-mcp ; REST task runs are initiated at `POST https://api.parallel.ai/v1/tasks/runs` and require status/result handling. Confirm the current REST endpoint details, supported schemas, idempotency and citation fields directly in the API reference before coding.
- Pricing: https://docs.parallel.ai/getting-started/pricing . Published list prices previously consulted indicated Fast/Turbo Search at $0.001/request, Basic/Advanced at $0.005/request, and Extract at $0.001/URL; Task prices depend on processor. Verify current prices, included results, minimum charges, account entitlements, tax and rate limits before setting cost reservations. The separate machine-payment gateway has different prices and is outside this plan.
- Cited extraction overview: https://parallel.ai/articles/ai-data-extraction-how-to-extract-structured-data-from-websites-at-scale . Vendor claims about source coverage and extraction are not acceptance evidence for this project.

## Target design and changes by subsystem

### Provider integration

- Add a dedicated Parallel HTTP adapter under `backend/marketing_backend/`, invoked from `providers.py` through explicit methods for search, extraction and, only if justified, asynchronous task submission/status/result. Use server-side secret configuration, never log keys, prompts, personal contact details or raw provider payloads. Add environment names and pricing settings to `.env.example`, `compose.backend.yml`, `compose.worker-pools.yml`, and deployment documentation; do not store credentials in tracked files.
- Normalize Parallel results into documented internal structures: source URL, final URL where available, retrieved content/excerpts, retrieval metadata and provider operation/status. Preserve source provenance and enough text for the application's existing exact evidence checks. Treat all third-party text as untrusted data. Validate redirect and URL boundaries; determine whether vendor extraction preserves the current robots, SSRF and content policies before replacing the local guarded fetcher.
- Extend `ProviderUsage` accounting and any database constraints for Parallel Search, Extract and Task. Reserve a conservative cost before each paid submission, including per-URL extraction and bounded task processor prices; account for polling and failed/uncertain requests according to verified provider billing rules. Never treat zero pricing as proof of a free plan. Keep global and product-line budgets, request caps and lease checks.

### Discovery and ownership evidence

- Replace Brave query execution in `discovery.py` and model-driven web assessment where Parallel can supply equivalent structured evidence. Keep bounded targets, tenant-specific ICP context, search exclusion memory, source filters and domain deduplication. Search results are leads, not verified company websites.
- Use Parallel's entity-discovery or research capabilities to propose the official company domain and its supporting sources. Preserve the distinction between a third-party source about a company and the company's proposed official website; retain citations and surface missing or conflicting evidence for human investigation.
- Replace the current same-clause and registry-allowlist heuristics with a documented policy suited to Parallel's actual responses, informed by synthetic and separately approved live evaluation. Keep basic URL, duplication and workspace checks, and do not equate a confidence score with guaranteed ownership. Preserve targeted retry lifecycle and the `SOURCE_INELIGIBLE` handling where applicable.
- Continue to store review candidates in `DiscoveryMemory`; a user must explicitly accept an eligible candidate. `discovery_api.py` must recheck saved identity/evidence and current context at acceptance, including older records. Existing historical candidates without adequate evidence stay reviewable for reassessment but cannot be accepted as verified.

### Research and contacts

- Adapt `stages.py` research and contacts to consume Parallel's structured data and sources. Ensure every material company fact and selected business contact retains a usable supporting source/excerpt; unsupported facts are rejected or flagged. Preserve existing stops for ambiguous identity, missing contact or insufficient evidence.
- Keep existing scoring, product matching and drafting contracts. Their model calls remain separately configurable; move xKiro calls out of web-intelligence paths without claiming xKiro is removed from the system. Do not use Parallel research output as automatic approval or authorization to send.
- If Task is needed, persist provider run ID and state before polling, bind it to workspace/job/idempotency context, resume after worker restart, cap polling and timeout, and prevent duplicate billable submissions after uncertain transport failures. Do not implement billing assumptions until Parallel's actual idempotency and polling rules are verified.

### Contracts, database, UI and operations

- Review `stage_contracts.py`, `worker_contracts.py`, `contracts.py`, `models.py`, `pipeline.py` and migrations. Add a new version only when a stored artifact shape changes; retain readers for existing v1/v2/v3 artifacts and avoid rewriting immutable history. Design a migration for any new provider-use and external-task fields, with upgrade, compatibility and rollback behavior tested on a disposable PostgreSQL database.
- Update `dashboard/app/native.py`, `dashboard/app/static/native.js` and backend response models to show provider/task status, source evidence, uncertainty/conflicts, and cost-related stops without exposing secrets. Preserve admin/operator/reviewer permissions and the separate acceptance action. Update the exported OpenAPI snapshot and BFF allowlists if public contracts change.
- Update `compose.backend.yml`, `compose.worker-pools.yml`, CI workflows, backend runbooks and `docs/ai` handoff owned by the lead. Keep Parallel-specific settings out of delivery pools. Keep scheduler/lease recovery operational and do not start other pools or change deployment ownership without authorization.

## Synthetic test and acceptance plan

- Adapter: mocked Search/Extract/Task success, pagination, malformed JSON, source/citation mismatch, blocked/unsafe URL, timeout, rate limit, provider outage, empty content, configuration failures, request limits and redacted diagnostics.
- Billing and concurrency: reservation before call, per-line/global exhaustion, uncertain submission, checkpoint recovery, lease loss, duplicate submissions, bounded polling, crash/restart and no automatic spend beyond approved budget.
- Discovery: same company on two workspaces/product lines, Wikipedia false positive, directory/association, official source versus third-party claim, conflicting domains, aliases, no source, source-ineligible retry, empty reassessment, failed job and preserved review history.
- Research/contact: exact citations, changed source, unsupported or ambiguous contact, absent sources, no source fabrication, prompt-injection text treated as data, provider outage and human review stops.
- Compatibility: old v1/v2/v3 artifacts and queued jobs; migration upgrade/rollback on disposable DB; restricted worker role/RLS; duplicate acceptance and stale context; BFF permissions and dashboard states.
- Run the focused offline suites, full isolated PostgreSQL backend suite, dashboard tests, API contract checks, and a synthetic actual API/BFF/worker journey. No production data or paid services in tests.

## Evaluation and rollout

1. Capture the exact current workspace changes and establish an isolated implementation branch/worktree without overwriting user work. Confirm the project entry-point docs against source and tests.
2. Implement and run synthetic tests first. Do not initiate Parallel account signup, purchases, provider calls, messages, or automatic cutover.
3. Prepare a live evaluation for explicit approval: specify the maximum number of discovery searches, Extract URLs, Task runs and processor, expected and maximum charge, selected workspace, and success/stop criteria. Evaluate official-domain precision, supported citations, useful candidates, false positives, uncertain/blocked sites, contacts, latency, and actual cost. Ask separately before spending; a configured monthly limit is not blanket approval.
4. Verify the outcome and record cost and limitations. Then prepare the local container update and migration, backup and rollback instructions for human approval. Production/DEV deployment, sender activation, and outreach require separate authorization.

## Decisions still open

- Parallel account access, credit balance and billing cycle, hard spending-limit/overage settings, current pricing, source coverage for Malaysia, data retention and allowed usage.
- Whether Search plus Extract meets the evidence contract or a Task processor is necessary; Task processor, cost cap and asynchronous recovery depend on verified API semantics.
- Which Parallel entity-resolution capability returns the most useful company-to-domain evidence, and which lightweight checks prevent observed false positives without reproducing restrictive custom heuristics.
- The replacement or continued use of xKiro for scoring/matching and creative drafting.
- Approved live-test sample, budget, quality threshold, cutover date and recovery owner.
