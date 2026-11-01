# Python Worker Redesign — Intern Task Brief

## Objective

Redesign the native Python worker architecture so each pipeline stage and delivery channel runs in an independently deployable process. Make worker failures easy to locate and keep each stage independently changeable through stable, versioned contracts. Support multiple product lines in one workspace: shared pools process work for all lines, while every task uses the correct line-specific ICP, discovery query, catalog, policy, and limits.

This is an implementation brief for the native backend in `backend/`. Start by reading `backend/README.md`, `docs/native-preparation-workers.md`, `docs/native-worker-migration-plan.md`, and the current worker/queue/pipeline/provider/sending code. The current implementation has one `marketing_backend.worker` loop, a PostgreSQL jobs table, JSON checkpoints/results, workspace-level catalog/settings, and separate delivery-attempt records processed in that same loop.

## Agreed architecture

### Process boundaries

Run one independently deployable process/pool per named job type:

- Setup
- Lead discovery
- Company research
- Contact finding
- Scoring
- Product matching
- Marketing content generation

Run delivery in separate channel pools:

- Email
- Social publishing/messaging
- Other approved messaging channels

A shared pool serves all product lines; do not deploy a separate copy per product line by default. Every job is scoped to one product line and its settings. Per-line concurrency, provider rate, and spend limits prevent one line from monopolizing a pool. Add a separate scheduler/recovery process for due discovery scheduling and expired delivery recovery.

Approval is performed by a human through the application/API. It is not an autonomous worker. It binds a decision to an immutable content snapshot, product line, channel, and context version. A delivery pool can only consume a task backed by an explicit valid approval.

### Product-line data ownership

Add a first-class `ProductLine` entity under a workspace. A product line owns its catalog entries, ICPs, targeting/discovery query, schedule, pause state, and configurable execution limits. A workspace can hold multiple lines.

Keep company identity unique at workspace scope and share sourced company/contact evidence within that workspace when current and applicable. Discovery candidates, preparation runs, scoring, matching, generated content, approval, and delivery are product-line-specific. Discovery for Product A must use Product A's ICP/query and context; Product B's task uses Product B's.

Migrate each existing workspace to one default product line and attach its existing products, ICPs, and automation settings to it. Preserve historical records and human decisions; do not silently reinterpret them as belonging to a newly changed context.

### Stage contracts and compatibility safeguards

Create versioned, strict input/output contracts for every stage. The task envelope must include:

- Workspace, product-line, company/lead/candidate, stage, idempotency key, and trace ID.
- Contract name and integer schema version, producer implementation version, and pinned product-line context version/hash.
- Bounded attempt/retry metadata and references to prior stage artifacts.

Persist successful outputs as immutable stage artifacts with schema version, validated payload, content hash, source/evidence references, producer version, and timestamps. Keep provider checkpoints separate from the stable artifact consumed by the next stage. Validate producer output before commit and validate it again at consumer entry.

Consumers must support the current and previous contract version. Additive optional fields may be introduced compatibly; any breaking field, meaning, or validation change requires a new contract version. Do not silently coerce unsupported contracts. Quarantine unsupported or malformed tasks with a persisted reason and diagnostic event. Provide an audited, idempotent replay path after a compatible consumer or explicit adapter is deployed. Retain old artifacts and decisions.

Pin every task to its product-line context version. If its ICP, discovery query, catalog, or policy changes while the task is running, mark its result stale and require new work. Do not interpret old output against new settings.

Discovery query generation, site fetching/scraping, evidence extraction, and assessment must be replaceable behind narrow interfaces. Record their strategy/implementation versions and relevant input hashes in the artifact. A discovery implementation change must not require changes to downstream consumers if the candidate contract stays compatible.

### Error handling and diagnostics

Use a shared failure taxonomy with stable sanitized code, category, and retryability. Distinguish at least configuration, provider transport/throttling, provider response/schema, evidence validation, budget exhaustion, stale context, lease loss, unsupported contract, and internal handler errors. Never include provider payloads, scraped page text, contact data, credentials, or message bodies in logs.

Emit structured logs with pool/stage, job ID, workspace ID, product-line ID, attempt, duration, contract version, trace ID, and sanitized error code. Persist append-only job/stage events for claim, checkpoint, retry, completion, failure, lease loss, quarantine, and replay. Keep a queryable current failure code/status. Make one pool's outage or backlog independent of other pools.

### Queue and runtime

Keep PostgreSQL as the queue for v1. Add pool/type filtering to claims so each process can only claim assigned job types. Continue using transactions, `FOR UPDATE SKIP LOCKED`, leases, heartbeats, checkpoints, RLS/workspace boundaries, and idempotency. A job must not be repeatedly claimed by a pool that cannot execute it.

Add worker commands/configuration that select exactly one pool and expose a process health/readiness status. Add Compose services for each pool, with independent restart policy, concurrency setting, and health check. Separate worker configuration from API configuration. Keep existing global provider ceiling and add per-product-line controls.

Social and messaging integrations do not currently exist in the native sender. Implement channel interfaces and synthetic/fake adapters for acceptance; do not make live provider calls or send real messages as part of this task. Email sending retains existing verified-sender, approval, and uncertain-handoff safeguards.

## Ordered implementation tasks

### Task 1 — Contract and event foundation

- Define shared task envelope and strict versioned schemas for existing stage inputs/outputs, beginning with discovery candidate output and research output.
- Add immutable stage artifact persistence and append-only job event persistence with appropriate workspace/product-line ownership constraints and indexes.
- Add validation at producer completion and consumer startup; add quarantine status/reason and audited replay metadata.
- Keep checkpoints internal to execution and out of the downstream contract.

### Task 2 — Product-line foundation

- Add `ProductLine` and ownership constraints beneath workspace.
- Move product/ICP association, automation preferences, discovery query/schedule, pause state, and limits to the line.
- Add product-line identity to discovery, candidate, preparation, scoring/matching, content, approval, and delivery records/jobs as applicable.
- Add a migration that creates one default line per existing workspace, backfills associations/settings, and preserves old records.
- Ensure the same company may be considered for multiple lines while workspace-level company identity/evidence remains shared.

### Task 3 — Typed worker processes

- Refactor execution into a common runner plus a registry of named pools; runner claims only its configured job type(s).
- Create independent process entrypoints/configuration for setup, discovery, research, contact finding, scoring, matching, and marketing content.
- Move scheduling and recovery out of stage execution into a scheduler/recovery process.
- Create separate email, social, and messaging delivery pools; isolate channel adapters and retain explicit approval validation at delivery time.
- Keep human approval in existing API/application flow and bind it to immutable product-line/channel-specific content snapshots.

### Task 4 — Diagnostics and deployment wiring

- Add structured sanitized logs, stable failure classes, persisted events, and pool health/readiness.
- Add Compose services and CI coverage for every process type. Use conservative configurable concurrency, default one in-flight task per product line per pool.
- Ensure a pool failure/backlog does not stop other pools and unsupported task types cannot be claimed accidentally.

### Task 5 — Canary and compatibility proof

- Deploy consumers supporting current and previous schema versions before introducing a producer version.
- Canary one product line and compare the new discovery implementation to current behavior. Compare candidate counts, evidence validity, duplicate rates, failures/quarantine, and provider usage.
- Keep old/new artifacts side by side. Expand to other product lines only after acceptance criteria pass.
- Roll back by routing new work to the prior producer; do not erase accepted candidate decisions, approved content, or audit history.

## Public interfaces and behavior changes

- Workspace APIs gain product-line create/read/update/pause/resume/list operations and product-line selection for discovery and preparation.
- Discovery and preparation requests carry a product-line ID; discovery uses that line's ICP/query/context.
- Job/operations APIs expose pool, product line, stage events, contract version, quarantine/replay status, and sanitized current failure reason. Never expose lease tokens or sensitive payloads.
- Content records identify asset type, immutable content snapshot, product line, intended channel, context hash, and approval state.
- Delivery records identify channel and approved snapshot; channel-specific processes report accepted, failed, or uncertain status.

## Acceptance criteria

- Two product lines in one workspace can run through the same discovery pool and receive different product-specific queries and ICP evaluation without cross-contamination.
- Shared company identity/evidence does not merge line-specific score, match, content, approval, or delivery state.
- Each pool claims only its assigned task types. Stopping or failing one pool does not block another pool's jobs.
- Current and previous contract versions are accepted; malformed/unsupported versions are quarantined with clear persisted reasons and can be replayed audibly after upgrade.
- A discovery implementation can change query/scraping behavior while unchanged downstream consumers accept the same candidate contract.
- Retries, lease expiry, worker restart, duplicate completion, and replay do not create duplicate artifacts, candidates, approvals, or deliveries.
- Product-line context edits invalidate old work and prevent stale results or approvals from advancing.
- No content can be sent without explicit approval for the exact immutable asset/channel/context snapshot. Social and messaging tests use fakes only; no live send/provider call is made.
- Existing workspace isolation, restricted worker DB role, provider budget ceiling, candidate human acceptance, draft approval, and uncertain delivery semantics remain enforced.

## Test approach

Use synthetic providers, synthetic company data, fake delivery adapters, and disposable PostgreSQL fixtures. Add focused contract/unit tests, migration/backfill tests, concurrent claim/lease tests, and actual multi-process integration checks. Run the backend test suite and running restricted-role API/worker smoke tests. Do not test with real prospect contact, paid provider calls, social posting, messaging, or SMTP delivery.

## Guardrails and reporting

- Work only in the native Python backend/Compose/CI paths required by these tasks. Do not modify legacy n8n workflows, production, DEV deployment, or send messages.
- Do not edit `docs/ai/` handoff/state/task-board files; the project lead owns them.
- Preserve existing unrelated workspace changes and do not stage or commit them.
- Before implementation, report the current branch and working-tree changes. Work on an isolated feature branch/worktree as directed by the lead.
- If a migration or compatibility decision falls outside this brief, stop that change and report the concrete conflict rather than silently changing the contract.
- Report changed files, migration behavior, test commands/results, known limits, and any follow-up required for live channel integrations.
