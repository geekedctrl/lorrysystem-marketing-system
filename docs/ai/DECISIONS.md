# Decisions

ADR-001 | 2026-10-10 | ACCEPTED
Context: existing application already owns workspaces, research, actions and approvals. Options: rewrite, reuse marketing actions as strategies, add bounded proposal record. Choice: preserve architecture and add one strategy-only entity, reusing auth, events, research and RLS. Consequence: proposals never confer approval to send; later conversion must pass existing immutable action approval.

ADR-002 | 2026-10-10 | ACCEPTED
Context: no approved live provider spend and runtime USD50 target. Choice: deterministic mock only, database constraint provider=mock, known zero generation charges, unknown future asset prices null. Consequence: live LLM quality and global monthly spend reservation remain future work; do not claim a billing cap exists.

ADR-003 | 2026-10-10 | ACCEPTED
Context: fresh evidence can still be insufficient for a channel. Choice: require sourced current primary contact/social evidence, allow no supported channels with warning, distinguish exact cited claims from suggested free-form copy. Context snapshots include contact/match/catalogue/research; edit resets review. Consequence: human contact and copy review remains essential and unsupported semantics are not automatically proven.

ADR-004 | 2026-10-10 | ACCEPTED
Context: root engineering brief requests specialist audits and model preferences. Choice: use the actual exposed collaboration API with inherited session models; CLI 0.160.0 checked, no persistent worker configuration or model switch. Consequence: preferred model identity not independently verified; no claim it was active.
