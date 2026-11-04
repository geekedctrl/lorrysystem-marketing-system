# Parallel AI web intelligence takeover

## Goal

Move web discovery and enrichment to Parallel so development can focus on qualification, content generation, social media, email drafts, and human review. This document records the current direction and the questions for more detailed planning; it does not authorize implementation, paid calls, sending, or deployment.

## Agreed direction

- Use Parallel for company discovery, finding official websites and corroborating sources, website evidence extraction, company research, and public contact discovery.
- Use Parallel's AI capabilities as the primary company-to-website entity resolver: request the proposed official domain, company identity, relevant details and supporting sources. Treat its output as a reviewable proposal, not an automatically accepted lead.
- Replace Brave Search and xKiro calls used for web-intelligence work. Parallel is intended to be the sole active web-intelligence provider after cutover, rather than a continuing side-by-side alternative.
- Keep product-specific qualification, scoring, matching, content generation, candidate review, and outreach approval in the application. Scoring, matching, and drafting still need a suitable model provider; whether to retain xKiro or select another provider remains open.
- Retain workspace isolation, durable jobs, leases, checkpoints, bounded retries, cost controls, source validation, and the separate human candidate-acceptance and outreach-approval gates. Provider citations alone do not prove a claim or company-domain relationship.
- Preserve existing candidates, leads, approvals, historical artifacts, and workspace changes. Retain a recovery path until the replacement has been verified.

## Proposed implementation

1. Map Parallel Search, Extract, and, where appropriate, Task APIs to the existing discovery, research, and contact-search contracts. Verify current documentation, model and account capabilities, source attribution, data handling, and pricing before deciding exact API modes.
2. Build a provider integration that maps Parallel's entity resolution, returned URLs, evidence, and structured data into existing worker contracts. Validate public URL safety, duplicates, workspace boundaries, and whether usable sources were returned; route missing or conflicting evidence to investigation and let a human review the proposed identity.
3. Integrate asynchronous provider tasks with the existing queue, including persisted task identifiers, lease and retry handling, duplicate submissions, uncertain billing outcomes, and recovery after interruption.
4. Reserve and record costs before provider requests using the project's budget controls. Keep credentials out of the repository and logs.
5. Switch the active web-intelligence path to Parallel after synthetic verification and an explicitly approved, capped live evaluation. Maintain human review and a documented rollback path.

## Verification and release gates

- Monthly Parallel API credit budget: $32. DigitalOcean hosting is a separate $12 monthly cost, making the stated combined amount $44 before other charges. Treat Parallel credit overage and other paid provider costs as outside the stated credits; do not assume the credit balance is a hard provider-side spending cap. Confirm billing settings and enforce a fail-closed application limit before live use.
- Use synthetic provider responses to test malformed outputs, unavailable sources, incorrect company-domain associations, unsupported citations, public-contact evidence, budget limits, retries, workspace isolation, and candidate-to-draft behavior.
- Establish live evaluation queries, measurable success criteria, and an explicit spending cap before requesting approval. No paid provider calls are authorized by this document.
- Verify provider pricing, account limits, data retention, and actual evidence quality before live use. Synthetic success does not demonstrate real-world discovery quality.
- Prepare the application update for human review after the checks pass. Do not deploy, publish, send outreach, or merge automatically.

## Questions to resolve in detailed planning

- Which Parallel APIs and modes best cover Malaysian company discovery, official-domain corroboration, research, and public contacts?
- How well does Parallel resolve official domains for Malaysian companies, trading names, subsidiaries, and third-party pages, and which lightweight source checks are justified by observed failures?
- What data may be sent to Parallel, what are its retention terms, and what provider-level and per-job limits should apply?
- Which generation model should support scoring, matching, email drafts, and social content after web-intelligence migration?
- How will existing in-flight jobs and versioned artifacts be handled at cutover, and how will rollback avoid duplicate provider work or charges?
- What quality, latency, cost, and human-review measures will determine whether the approved live evaluation is successful?

## References

- [Parallel documentation](https://docs.parallel.ai/home)
- [Parallel pricing](https://docs.parallel.ai/getting-started/pricing)
- [Parallel Task MCP and asynchronous research](https://docs.parallel.ai/integrations/mcp/task-mcp)
