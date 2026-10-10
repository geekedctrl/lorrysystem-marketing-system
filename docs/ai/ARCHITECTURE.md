# Architecture

Current: FastAPI owns authenticated workspace data, PostgreSQL RLS enforces isolation, dashboard accesses only the API, n8n performs bounded research/preparation. See ../PRODUCT_WORKSPACES.md, ../lead-preparation-pipeline.md and ../../integrations/n8n/README.md.

Campaign proposal is a distinct strategy record, not a marketing action. Qualified lead + recent completed research + fresh citations + active matched product feed deterministic mock inference. Strict schema validates cited claims. A context fingerprint guards edits/review, optimistic versions prevent lost updates, workspace-scoped idempotency prevents duplicate generation. Human review records REVIEWED/REJECTED without outbound approval. Edits reset review to DRAFT. Migration 015 applies force RLS and composite workspace foreign keys.

Live LLM/image/video adapters, billing reservation and generated asset storage remain future work. No new queue infrastructure is introduced.
