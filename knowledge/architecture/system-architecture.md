# System architecture

Updated: 12 October 2026.

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Dashboard | Python FastAPI, Jinja2, custom CSS, vanilla JavaScript | Signed-in workspace UI, company/contact overview, candidate review, research brief and approval screens. |
| Marketing API | Python FastAPI, SQLAlchemy, Pydantic | Authentication, authorization, workspace context, lifecycle rules, queues, guarded retrieval and persistence. |
| Database | PostgreSQL, Alembic | Persistent records, workspace ownership and row-level isolation. Feature migration head: `011`. |
| Target orchestration | Python workers + PostgreSQL durable queue | Workspace-bound discovery/research, contact search, scoring, matching and drafting, ending at human approval. Native implementation is being prepared for parallel DEV validation; n8n remains in the current deployed runtime until cutover. |
| Search | Brave Search API | Company discovery, public source evidence and indexed professional-profile lookup. |
| Model gateway | xKiro, compatible Chat Completions API | Structured company/ICP research using `mistralai/mistral-large-2512`. Base URL: `https://api.xkiro.com/v1`. |

The native dashboard accesses business data through the native Marketing API. The native worker uses its own restricted database role for durable claims and stage persistence. PostgreSQL row-level policies and relationship checks preserve workspace isolation. Legacy dashboard/API/n8n remain a separate deployed runtime during migration.

The lifecycle is candidate discovery, human acceptance, company research/people lookup, contact review, qualification/scoring, matching, drafting and approval. The [preparation pipeline](../automation/lead-preparation-pipeline.md) implements the sequence through approval; sender execution/tracking remain next work. Migration 011 and the application update must be deployed before its worker claims jobs.

One app can serve unrelated products with independent teams and catalogs. In the target runtime, shared Brave/xKiro worker credentials are configured once for the platform; product-specific data and permissions live in the workspace. Encrypted in-app provider management and sender identities still need migration work.

Implementation references: [workspace access and migration guide](../../docs/PRODUCT_WORKSPACES.md), [n8n integration package](../../integrations/n8n/README.md), [API entry point](../../api/app/main.py), [dashboard entry point](../../dashboard/app/main.py), [migration sources](../../database/migrations/versions/).
