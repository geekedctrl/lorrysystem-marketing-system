# Worker redesign workspace

This ignored folder is the working area for redesigning the Python workers. Keep drafts, architecture decisions, migration notes, and local experiments here while the design evolves. Nothing in this folder is committed.

## Direction

Move from one process that polls and executes every job type to independently scalable worker pools. Work is isolated by workspace and product line, and every stage consumes and emits explicit versioned records.

## Proposed worker pools

1. **Discovery** — find companies, fetch initial evidence, and create candidates. Candidate acceptance remains a human decision.
2. **Research** — build and persist a sourced company profile, including evidence gaps.
3. **Contact finding** — identify relevant people and supported public contact channels.
4. **Scoring and matching** — score each company against each applicable product line and select eligible offerings.
5. **Marketing content** — generate tailored brochures, posters, email drafts, and other requested assets using approved product facts and sourced company evidence.
6. **Sending** — deliver only content tied to an explicit human approval; record accepted, failed, or uncertain outcomes.

Approval is a human workflow gate exposed through the application, not an autonomous worker. The approval record must bind the decision to an immutable content snapshot and its product-line/context version.

## Core design rules

- A task carries workspace, product-line, company/lead, stage, idempotency key, context version, attempt policy, and trace identifiers.
- A company is stored once per workspace; research can be shared where appropriate, while fit, score, match, content, approval, and campaign state are product-line specific.
- Each worker pool claims only its supported task types. Pools can scale and deploy independently.
- Apply per-workspace and per-product-line concurrency, rate, and budget limits, alongside the existing global provider ceiling.
- Persist stage outputs before scheduling downstream work. Retries must be bounded and idempotent; uncertain provider or delivery outcomes must remain explicit.
- Preserve lease ownership, workspace isolation, candidate acceptance, approval, and sending safeguards through migration.
- Add queue age, throughput, retries, failures, provider usage, and per-pool health metrics before increasing concurrency.

## Migration outline

1. Define product-line identity, lifecycle, and versioned task/result contracts.
2. Add product-line-scoped assessment and preparation records while retaining workspace-level company identity and reusable evidence.
3. Separate scheduling from execution and route jobs to typed queues with fair per-product-line claiming.
4. Extract worker pools incrementally: discovery, preparation stages, content, then sending.
5. Shadow-run against synthetic fixtures, compare persisted results, and verify retry/lease/pause/approval behavior.
6. Move one product line at a time with one active executor per capability and a documented rollback path.

## Open design decisions

- Which catalog entities represent a product line versus a product/SKU?
- Can company research and contact evidence be shared across product lines, and what freshness rules apply?
- Is scoring always per product line, or can shared attributes be computed once and combined with line-specific fit?
- Which content types are required first, and what assets need a separate generation provider or approval policy?
- What queue technology and deployment topology fit expected volume? Start with PostgreSQL-backed typed queues unless measured throughput requires a broker.
- What are the default concurrency, retry, retention, and budget policies per pool and product line?
