# Repository map

Updated: 6 October 2026.

| Path | Intent |
| --- | --- |
| `api/app/routers/` | API endpoints, workspace access and HTTP error contracts. |
| `api/app/services/` | Business lifecycle, research completion/industry promotion, candidate acceptance and fetch rules. |
| `api/app/schemas/` | API request/response schemas. |
| `api/app/models/` and `api/app/db/` | Persistent models, sessions and workspace ownership. |
| `api/scripts/` | Disposable integration and migration regressions. |
| `dashboard/app/main.py` | Server-rendered dashboard routes. |
| `dashboard/app/templates/lead_detail.html` | Company/contact overview and lead page ordering. |
| `dashboard/app/templates/research_brief.html` | Research brief, people/profile cards, evidence and history. |
| `dashboard/app/research_presenter.py` | Saved-report presentation and safe links. |
| `dashboard/app/static/` | Custom CSS and browser JavaScript. |
| `database/migrations/versions/` | Alembic migration chain; feature branch head `011`. |
| `integrations/n8n/dashboard-discovery.js` | Generate the workspace-bound dashboard discovery dispatcher. |
| `integrations/n8n/research-workflows.js` | Generate research child/queue workflows. |
| `integrations/n8n/research-runtime.js` | Seed/evidence/model validation and structured industry output. |
| `integrations/n8n/people-runtime.js` | Professional URL parsing, named-person queries and evidence matching. |
| `api/app/routers/pipeline.py`, `api/app/models/pipeline.py` | Human reviews and workspace-scoped stage queue/completion. |
| `dashboard/app/templates/lead_stage_controls.html`, `lead_stage_overview.html` | Human stage controls and six-stage navigation. |
| `integrations/n8n/pipeline-workflows.js`, `pipeline-runtime.js` | Generate stage child/worker and validate workspace evidence/model output. |
| `integrations/n8n/workspace-preflight.json` | Importable workspace preflight template. |
| `docs/` | Version-controlled deployment and feature documentation. |
| `.github/workflows/` | CI and trusted develop deployment dispatch. |
| `knowledge/` | Local current guidance and clearly marked historical documents. |
| `tmp/`, `.env*`, runtime data | Ignored private/local material; never treat these as deployable artifacts. |

Start with [system architecture](../architecture/system-architecture.md) for the relationships between these components. The earlier intern structure guide is retained as [historical reference](../archive/development/repository-structure-baseline.md).
