# Native preparation workers

Implemented locally on 11 October 2026 in the independent `backend/` application. This backend executes the shared preparation pipeline without n8n. The existing deployed dashboard/API still use their original integrations; this change is not an executor cutover.

## Product and team flow

1. A platform administrator creates a workspace and assigns its administrator through the existing backend account commands.
2. The administrator enters actual offerings using the catalog API and activates automation with a product description, optional target customers, country, language, voice and batch size (1–10, default 3).
3. Product setup prepares targeting/search. Existing ICPs are preserved; missing ICPs may be generated from the authoritative catalog. Discovery runs on the workspace's daily schedule or an explicit operator request.
4. Discovery accepts only sourced, identity-supported official companies with a valid workspace ICP and confidence of at least 75. Lead creation and its research job are transactional.
5. Research, contact search, scoring, matching and drafting advance automatically when their evidence/policy gates pass. A successful run creates one immutable draft snapshot and pending approval.
6. Administrators or Reviewers can approve, reject or request changes. No handler or endpoint sends a message. Requested changes currently require a fresh preparation run rather than an inline draft editor.

The worker consumes all products through one Python handler registry. Workspace catalog/targeting and the selected ICP travel in a versioned snapshot; no product-specific scripts or n8n bindings are needed.

## Native stages and limits

| Stage | Behavior |
| --- | --- |
| SETUP | Generate a search plan and up to five missing ICPs; never create new product features. |
| DISCOVERY | Up to three public searches, five results per search and ten fetched new domains. Normalize domains conservatively, skip workspace memory/known leads, retain unsuccessful domain decisions and atomically accept supported candidates. Batch size is an upper limit, not a guaranteed number. |
| RESEARCH | Homepage plus prioritized official team/contact/about/services pages, up to six pages. Save fetched evidence and unavailable coverage. Validate literal quotes, named people, roles and public contact fields. Persist sourced industry and company facts in the research result. |
| CONTACT_SEARCH | Up to five supported people, two queries each. Publicly indexed individual LinkedIn and relevant professional X/Twitter, GitHub and Instagram profiles require name/company evidence; other professional handles also require role evidence. Multiple matches stay unresolved. No platform login or profile-page scraping. |
| SCORING | Default ICP fit40, operational need30, scale15, buying signals10, evidence quality5. Custom validated ICP rubrics can total100. Need/signals require observed category-specific evidence. Save separate relevance/opportunity components and adjustments. Default automatic qualification requires total60 and positive ICP fit. |
| MATCHING | Match only active snapshot products with sourced support. Select the best eligible match at fit60 or above. Unsupported/low-fit products do not advance preparation. |
| DRAFTING | Use actual product capability, current evidence, supported contact, channel, voice and language. Create one email or individual LinkedIn draft for review. Recipient/channel are assigned by validated application data rather than model output. |

Existing technology does not establish an unmet need. Free-form interpretation and draft prose remain suggestions requiring human judgment; exact citations validate source support, not the semantic truth of every generated sentence. Synthetic calibration verifies that capability alone can result in a45 score with zero opportunity and a qualification stop.

Standalone `/research` remains available for manual homepage review, but it now uses the same provider ledger as managed preparation. `/prepare` runs the full native chain. A manually prepared lead can choose an ICP code; absent a code, the first configured ICP is used. Discovered companies retain their selected ICP.

## Clear exceptions and continuation

No supported person/channel, ambiguous identities, insufficient company evidence, low qualification, unavailable matching and provider failures have distinct reasons. Source links and historical results remain available.

For a contact stop, an Operator or Administrator can choose a saved researched person/profile or enter a business contact whose name, role and email are supported by an exact saved official-company quote. This records the human actor and continues scoring using the existing research. Another explicit contact-search attempt reuses research and refreshes search checkpoints. Unsupported or uncited manual contacts are rejected.

Missing public evidence that was never fetched still requires a new research run; uploading external/manual evidence and resolving private known contacts are not implemented yet. Low qualification/match stops do not have a manual override in this version.

Pause disables claims and rejects running completion. Interrupted jobs stop with PRODUCT_PAUSED and require explicit retry after resume. Pending setup can be resumed before a query exists. Catalog editing while automation is running is blocked when work is outstanding; editing after pause invalidates pending work. Changed catalog/targeting blocks stale completions/retries and approval. A newer preparation run also makes older draft approval stale.

Job history records start, completion, failures and human retries/resolution. Operations reports select the latest preparation per lead, avoiding old failed attempts becoming current warnings. Full history remains under the lead preparation/job endpoints.

## Provider configuration and reservations

Platform operators configure Brave and xKiro once using the ignored local development configuration. Workers receive credentials; products and operators do not need per-workspace keys. Bootstrap variables are listed in [backend/.env.example](../backend/.env.example). Shared encrypted in-app credential management/rotation remains a cutover requirement.

Required configured rates are input/output USD per million model tokens and search USD per request. Missing credentials or rates fail before provider calls. xKiro supports the configured Authorization bearer header or `x-api-key`; HTTPS provider origin is validated. Provider endpoints never follow redirects automatically.

Before each request, PostgreSQL serializes a monthly global API-provider allowance reservation. Default allowance is USD50 for this independent backend's providers; it excludes hosting, legacy calls and other systems. Reservations use a conservative model input-byte bound with framing allowance and maximum output, or configured search rate. Actual reported token counts are saved separately. Rates must be confirmed by platform operations; these estimates are not reconciled invoices or a guarantee of total platform expenditure.

Retries consume allowance; uncertain transport calls remain reserved. Each job allows at most24 provider reservations across attempts and explicit retries. Brave calls are paced globally at least1.5 seconds apart. Provider JSON/search results and fetched pages are checkpointed. Automatic retry is bounded for transient failures; permanent failures stop. Explicit failed-job retry retains fetched/search evidence while discarding old model output, so invalid cached responses can be regenerated.

## API commands

All routes below are under `/workspaces/{workspace_id}` and require an expiring bearer session plus membership. Workspace records use forced PostgreSQL row-level policies.

| Route | Purpose / role |
| --- | --- |
| `POST /automation/activate` | Administrator product setup with idempotency key |
| `POST /automation/pause`, `/automation/resume` | Administrator execution control |
| `POST /discovery` | Administrator/Operator bounded batch with idempotency key |
| `POST /leads/{lead_id}/prepare` | Administrator/Operator native preparation; optional ICP code |
| `GET /leads/{lead_id}/preparation` | History with explicit current-run marker |
| `GET /preparation/{run_id}` | Current/historical stage results and stop reason |
| `POST /preparation/{run_id}/contact` | Select supported person/profile or source-backed manual business contact |
| `POST /preparation/{run_id}/retry-contact-search` | Explicit retry without repeating research |
| `GET /approvals` | Saved approval snapshots and stale-context flag |
| `POST /approvals/{approval_id}/decision` | Administrator/Reviewer decision; never sends |
| `GET /operations` | Current run states, stalled/delayed jobs and recent provider status/usage |
| `GET /jobs`, `/jobs/{job_id}` | Job status/history, next availability and lease expiry, never lease token |
| `POST /jobs/{job_id}/retry` | Administrator/Operator explicit failed-job retry |

Requests are strict structured JSON. Activation accepts `product_description`, `target_customers`, `country`, `language`, `brand_voice`, `batch_size` and `idempotency_key`. Preparation accepts `idempotency_key` and optional `icp_code`. Contact resolution accepts either `person_index` plus optional `profile_url`, or `business_contact` with name, role, email, optional phone, source_url and evidence_quote. Approval decision accepts decision and a review note.

## Storage and reliability

Independent migrations003–005 add preparation runs, workspace discovery memory, provider reservations, approvals, workspace automation settings and strengthened job ownership. Results are typed at handler boundaries and stored per stage as bounded JSON with supporting source text. Composite keys bind every managed lead job to the same workspace and lead as its run.

Completion holds the owned unexpired job lease, verifies active workspace/product and context, saves the result and next stage/approval in one transaction. Unique stage/active-run constraints prevent duplicate progression. The trusted cross-workspace worker cannot read user/password/session tables or update approval decisions. PostgreSQL also enforces pending initial approvals and immutable snapshot/ownership fields. API decisions use a separate role and membership checks.

Migration003 downgrade deliberately refuses to destroy preparation/approval history. Export/reconcile records and use an explicit recovery migration instead.

## Acceptance and remaining work

Local PostgreSQL integration tests cover the foundation and native chain, six synthetic companies across transport/accounting catalogs, opportunity gating, public source checks, deeper-page checkpoints, profile ambiguity, manual contact continuation, refreshed contact search, transactions, stale approval, pause/resume, ownership, actual restricted worker role and provider budget/cache/throttling contracts. A running HTTP API/worker smoke test uses their actual restricted database roles and confirms missing credentials make no provider calls.

Tests use deterministic synthetic company/provider data. They do not demonstrate real Brave/xKiro quality or actual sending. Before replacing the deployed executor: real-provider calibration with approved allowance, encrypted provider connections, dashboard adaptation, data/account/approval migration, separate sending parity and one-executor ownership/rollback checks remain required. Current n8n workflows are untouched. PR base is always `develop`; production is separate.
