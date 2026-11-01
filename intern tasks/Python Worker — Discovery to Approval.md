# Task: Revamp the Python Lead-Preparation Worker, Discovery Through Approval

## Description

Improve the native Python worker pipeline so it finds relevant companies from trustworthy public evidence, researches each accepted lead, identifies people demonstrably connected to that specific company, scores prospects with an understandable matrix, matches qualified leads to real workspace products, and prepares a draft that waits for human approval.

The goal is better evidence quality and explainability—not more records at any cost. Build on the current Python worker, API, PostgreSQL ownership/lease model, provider-budget reservations, and workspace isolation. Start from source and executable tests because older documentation can be stale. Preserve the explicit human-review stages: discovered companies remain candidates until a human accepts them; outreach drafts remain pending until a human reviewer decides; approval never sends a message.

When a draft becomes pending approval, the system should notify the configured reviewer destination via **ntfy for now**. Treat this as an alert only. Keep server/topic/optional auth configuration outside source control; use a fake transport in tests. Do not send to a real ntfy server/topic or call live search/model providers until the project owner explicitly approves that test and destination.

Create a dedicated branch from the latest `develop` in `geekedctrl/lorrysystem-marketing-system`. Submit a pull request targeting `develop`; do not merge or deploy.

## Where to start

| Area | Files to inspect | What to learn |
|---|---|---|
| Worker entry and job safety | `backend/marketing_backend/worker.py`, `queue.py` | How jobs are claimed, leased, heartbeated, checkpointed, completed, retried, and failed. Keep provider/network work outside database transactions and never save stale lease results. |
| Stage order and durable transitions | `backend/marketing_backend/stages.py`, `pipeline.py` | Stage schemas/handlers, workspace/product snapshots, next-job scheduling, stop reasons, and when pending approvals are created. `queue.complete()` calls `pipeline.finalize()` and commits the stage result and next transition together. |
| Company discovery | `backend/marketing_backend/discovery.py`, `discovery_api.py`, `public_fetch.py`, `scraping.py` | Search query construction, directory filtering, bounded same-domain crawling, SSRF/DNS/robots protections, candidate evidence, retry memory, candidate review, and explicit acceptance. |
| Research and people | `backend/marketing_backend/stages.py` (`research`, `contacts`), `research.py`, `public_fetch.py` | Page selection/limits, quote validation, partial findings, public people extraction, profile search, ambiguity handling, and safe contact continuation. |
| Score and product match | `backend/marketing_backend/stages.py` (`rubric`, `scoring`, `matching`) | Default and per-ICP rubric validation, evidence requirements, score arithmetic, qualification gate, product fit threshold, and stop reasons. |
| Data contracts and persistence | `backend/marketing_backend/contracts.py`, `models.py`, `migrations/versions/003_native_preparation.py`, `008_discovery_review.py`, `004_approval_snapshot_guard.py` | Existing typed response shapes, durable run/candidate/approval storage, constraints, and immutable review snapshots. Ask the owner before adding or changing a migration/API contract. |
| Provider safety and cost | `backend/marketing_backend/providers.py`, `backend/.env.example` | Search/model calls, cached checkpoints, conservative reservations, rate pacing, provider configuration, timeouts, and failure classification. Do not bypass these controls. |
| Existing acceptance tests | `backend/tests/test_discovery_review.py`, `test_native_pipeline.py`, `test_backend.py`, `native_acceptance.py`, `native_acceptance_check.py` | Synthetic provider fixtures and regression coverage for candidate acceptance, citation gates, scoring, profile ambiguity, retries, ownership, and pending approvals. |
| Local test stack | `backend/README.md`, `compose.backend.yml` | Isolated `marketing-rebuild` Compose project and `marketing_rebuild_test` database. Use only the documented disposable test database/project. |

Useful source landmarks (line numbers may change): `stages.py` defines `research()` near the start of its handler section, `contacts()`, `DEFAULT_RUBRIC`, `rubric()`, `scoring()`, `matching()`, and `drafting()` later in the file. `discovery.py` contains `discovery_queries()`, `assess()`, and `discover()`. `pipeline.py` contains `start()`, `finalize()`, and `schedule()`.

## How to approach the problem

1. Read the existing implementation and tests before proposing behavior changes. Make a short stage diagram with each input, output, evidence source, persisted checkpoint, and stop condition.
2. Reproduce important current behavior with synthetic fixtures. Identify specific false positives, missing useful data, confusing score outcomes, and failure paths; do not optimize for volume alone.
3. Write down the proposed scoring rubric and examples before changing weights, thresholds, or qualification policy. Get owner approval for policy changes; implementation details that preserve current policy can proceed on the task branch.
4. Make bounded changes one stage at a time. Validate outputs at the boundary, keep citations tied to fetched pages, and return useful partial results when a single fact/contact is bad.
5. Add synthetic regression tests alongside each behavior change. Keep search/model calls behind the existing `Providers` abstraction so tests never call external providers.
6. Design the ntfy notification as a post-commit, idempotent event. Do not issue an HTTP request from `pipeline.finalize()` while its database transaction is open. Prefer a durable outbox/event committed atomically with the pending approval, then dispatch it after commit with bounded retry. If that requires a schema migration or new shared configuration, submit the design for owner review before implementing it.
7. Run focused tests, then the documented full backend suite. Review the final diff for scope, secrets, real data, provider calls, and accidental changes to legacy/n8n or deployment behavior.

## Scoring baseline to verify in source

The current documented/default matrix is a 100-point maximum:

| Criterion | Maximum points | Evidence/interpretation to verify |
|---|---:|---|
| ICP fit (`icp_fit`) | 40 | Evidence the company matches the selected workspace ICP; positive points require citations. |
| Operational need (`operational_need`) | 30 | An observed, source-backed `PAIN_POINT`; existing capabilities/technology alone are not a need. |
| Operating scale (`operating_scale`) | 15 | Source-backed scale signals relevant to the ICP. Do not infer fleet size or revenue without evidence. |
| Buying signals (`buying_signals`) | 10 | An observed, source-backed `SIGNAL`; do not convert ordinary capability statements into intent. |
| Evidence quality (`evidence_quality`) | 5 | Quality/support of the underlying evidence, not confidence invented independently of sources. |

Current source is expected to require rubric criteria to be unique, valid, positive integer maxima totaling 100; each returned criterion must be within its maximum and every positive score must cite saved evidence. Quotes must match saved research pages. Unsupported operational-need or buying-signal points are adjusted to zero unless supported by an observed fact of the corresponding category. The current qualification gate is total score `>= 60` **and** positive ICP-fit points. Verify every item in `stages.py` and its tests before relying on this summary.

The result also separates `relevance` from `opportunity`: relevance excludes operational need and buying signals, while opportunity contains those two criteria. Existing regression tests demonstrate a capability-only case scoring 45 with zero opportunity and stopping at `QUALIFICATION_BELOW_POLICY`. Preserve and explain this distinction. Do not change weights/thresholds without owner approval. If the rubric is revised after approval, include before/after synthetic examples and boundary tests.

## 10-step checklist

- [ ] **1. Map and baseline the pipeline.** Trace `worker.py` → `stages.dispatch()` → `pipeline.finalize()` for discovery and all preparation stages. Document stage inputs/outputs, snapshot/context validation, job idempotency, retry/lease behavior, provider reservations, stop reasons, and approval creation. Run relevant existing tests first and record the baseline.
- [ ] **2. Improve company discovery.** In `discovery.py`, assess query relevance to the selected ICP/product and geography, official-company/operator/buyer identity, homepage/domain handling, directory/vendor false positives, deduplication, bounded page budgets, candidate evidence, and per-company failures. Preserve `public_fetch.py` safety checks and `DiscoveryMemory` behavior. Discovery must save review candidates only; `discovery_api.py` human acceptance remains the only route that creates the lead and starts research.
- [ ] **3. Improve lead research.** In `stages.research()` and its schemas/helpers, review the homepage plus prioritized official company pages, the six-page cap, identity check, exact contiguous quote validation, fact categories, confidence/kind, unknowns, and partial-failure handling. Improve relevance and coverage without relaxing source checks or fabricating claims. Keep a failed/missing page as an explicit gap when other pages still provide useful supported findings.
- [ ] **4. Improve finding people connected to the lead.** Review research people extraction and `stages.contacts()`: current research caps people at five; public profile search uses name/company and (for non-LinkedIn sources) role evidence; multiple matches remain candidates rather than a selected profile. Strengthen name/company/role association and explain why a person/profile is supported. Never guess emails/phones, scrape login-gated pages, conflate same-name people, or silently select ambiguous profiles. Preserve the human contact-resolution path when no supported contact is available.
- [ ] **5. Specify and review the scoring matrix.** Verify `DEFAULT_RUBRIC`, `rubric()`, `normalize_score_output()`, `scoring()`, `ScoreOutput`, and current tests. Write the criteria, weights, scoring scale, positive-evidence rules, missing/unknown treatment, `relevance`/`opportunity` math, qualification gate, and worked examples in a reviewable note. Ask the owner to approve any change to business criteria, weights, or thresholds before implementing it.
- [ ] **6. Make scoring explainable and robust.** For the approved matrix, return/store one result per criterion with points, maximum, rationale, cited evidence, and explicit unknowns/adjustments where the existing contract permits. Validate exact criterion coverage, bounds, citation provenance, totals, and qualification deterministically. Add tests for zero/missing evidence, unsupported need/signals, low and high boundaries, invalid/duplicate criteria, custom ICP rubrics, and model output aliases. If an API/schema change is needed, stop and request owner review before changing contracts or migrations.
- [ ] **7. Verify matching and drafting gates.** Inspect `matching()` and `drafting()` and their schemas. Confirm only active products from the captured workspace context can match, positive fit has source evidence, unsupported/low-fit matches stop, the selected product is actually in the catalog, recipient/channel are derived from validated contact data, claims cite research, and unsupported promises are rejected. Test each stop condition and prove no draft is created when required evidence/contact/qualification is missing.
- [ ] **8. Complete the human approval flow and ntfy alert.** Inspect `pipeline.finalize()` and `Approval` persistence. Keep the draft snapshot immutable and status `PENDING`; approval remains an explicit authorized reviewer action and is separate from sending. Add a configurable ntfy notification for a newly pending approval using a post-commit idempotent outbox/event design, bounded retry, redacted safe message, and no sensitive lead/contact content. A failed notification must not fail or approve the draft. Add fake-transport tests for success, duplicate event, timeout/failure, and retry. Never send a real ntfy notification without explicit owner approval.
- [ ] **9. Run synthetic end-to-end acceptance.** Extend `test_discovery_review.py` and `test_native_pipeline.py` (and other focused tests only as needed) with synthetic companies, people, pages, evidence, score cases, and fake providers/ntfy. Cover candidate acceptance/rejection, duplicate/retry, unsupported evidence, ambiguous person, every score gate, catalog/context staleness, workspace isolation, pending immutable approval, notification idempotency/failure, and the invariant that approval/notification never sends outreach. Do not use live accounts, real company/contact data, or paid providers.
- [ ] **10. Open the requested PR.** Create/push only the dedicated task branch and open a PR to `develop` in `geekedctrl/lorrysystem-marketing-system`. Include architecture/stage map, discovery/research/people behavior, exact approved scoring matrix and examples, ntfy configuration and failure semantics, changed files, test commands/results, limitations, and any migration/API-contract decisions. Scrub secrets, topics, personal data, and real provider payloads from logs/screenshots. Request owner review; do not merge, deploy, or run live provider/ntfy tests.

## Local verification guidance

Follow `backend/README.md` and use only the isolated `marketing-rebuild` project and `marketing_rebuild_test` database. The root `.env` is private local configuration; never print it or include it in the PR.

From PowerShell, the documented full backend test command is:

```powershell
docker compose --env-file .env -p marketing-rebuild -f compose.backend.yml --profile test run --rm --build backend-test
```

If the isolated database has not been created yet, start only its database service and create the explicitly named test database once, as documented in `backend/README.md`. Never point tests at DEV, production, a developer's working database, or another Compose project. Do not use broad `down --volumes` cleanup commands; ask the owner before removing any database volume. If Docker/database setup blocks testing, report the exact blocker rather than switching to a live environment.

## Boundaries and definition of done

- Limit changes to the native Python worker/backend and the tests/docs required for this assignment. Ask before changing API contracts, migrations, frontend files, deployment/CI release configuration, or unrelated legacy/n8n behavior.
- Provider search/model calls remain bounded by existing reservation, rate-limit, timeout, and fetch-safety controls. Do not add unbounded crawling, retries, or model calls.
- Source evidence enables review; it does not prove the semantic truth of every generated claim. Keep uncertainty visible and human review mandatory.
- No committed provider credentials, ntfy server/topic/token, real lead/contact data, real provider payloads, or private notification content.
- All relevant synthetic tests pass; the full isolated backend suite passes or has a specific reproducible environment blocker.
- PR targets `develop`, includes a clear summary/tests/limitations, and is left open for owner review. No merge, deployment, live provider call, real ntfy send, approval, or outreach send is performed by the intern.
