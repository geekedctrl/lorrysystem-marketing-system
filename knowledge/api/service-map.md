# API services and workflow boundaries

Updated: 7 October 2026. Read the router/schema sources for exact payloads; old API-completion handoffs are historical.

| Service | Responsibility | Source |
| --- | --- | --- |
| Workspaces and identity | Email/password login, memberships, roles, catalogs, settings, named service credentials and automation context. | [Workspace router](../../api/app/routers/workspaces.py) |
| Candidates | Discovery evidence, review and human acceptance. | [Candidate router](../../api/app/routers/candidates.py) |
| Discovery runs | Workspace Find Leads request/claim and run state. | [Discovery-run router](../../api/app/routers/discovery_runs.py) |
| Companies and contacts | Official company/contact records, independent of suggested people in a research report. | [Companies](../../api/app/routers/companies.py), [Contacts](../../api/app/routers/contacts.py) |
| Leads | ICP-bound lifecycle, activity and closure rules. | [Lead router](../../api/app/routers/leads.py) |
| Research | Pending/running/complete/partial/failed runs, workspace claims, evidence sources, retry and stale recovery. Completed research can promote missing industry from supported saved evidence. | [Research router](../../api/app/routers/research.py), [schemas](../../api/app/schemas/research.py) |
| Guarded public fetch | Bounded public retrieval for named workspace automation. | [Public fetch router](../../api/app/routers/public_fetch.py) |
| Scoring and qualification | Evaluate fit and lifecycle eligibility using research/ICP context. | [Scoring router](../../api/app/routers/scoring.py) |
| Product matching | Evaluate catalog offerings for a lead. | [Product matching router](../../api/app/routers/product_matching.py) |
| Marketing actions | Persist draft/action state and controlled execution transitions. | [Marketing-action router](../../api/app/routers/marketing_actions.py) |
| Approvals | Human approval decisions with reviewer/admin authorization. | [Approval router](../../api/app/routers/approvals.py) |
| Reviewed preparation queue | Contact review, human qualification, workspace stage requests/claims/context, atomic score/match/draft completion, stale guards and safe retries. | [Pipeline router](../../api/app/routers/pipeline.py), [feature guide](../../docs/lead-preparation-pipeline.md) |

Core research endpoints include `POST /api/leads/{lead_id}/research`, `POST /api/research/claim?max_running=1`, `GET /api/research/{research_id}/context`, source creation, completion/partial/failure transitions and `POST /api/research/recover-stale`. Named credentials scope queue claims and reads to their workspace.

The new n8n stage pair handles scoring, matching and drafting after explicit human requests. Its health gate waits for API migration 011 deployment. Existing discovery/research remain separate. Approval and sender/delivery actions remain human/later-stage controls; no new sending workflow is activated.
