# Marketing system knowledge

Updated: 14 October 2026. This is the entry point for the current project context.

Start with [Current status](status/current-status.md), then [System architecture](architecture/system-architecture.md) and [Product workspace roadmap](product/product-workspaces-roadmap.md). Current guidance supersedes dated build instructions in the archive. Latest release verification is recorded in [Current status](status/current-status.md).

| Purpose | Read |
| --- | --- |
| Implementation status and next work | [Current status](status/current-status.md), [14 October changes](status/2026-10-14-change-log.md), [13 October changes](status/2026-10-13-change-log.md), [12 October changes](status/2026-10-12-change-log.md), [7 October changes](status/2026-10-07-change-log.md), [6 October changes](status/2026-10-06-change-log.md) |
| Product scope and ideal customers | [Workspace roadmap](product/product-workspaces-roadmap.md), [LorrySystem ICP](product/lorrysystem-icp.md) |
| Dashboard layouts and user journeys | [Dashboard UX redesign](product/dashboard-ux-redesign.md), [original brief](archive/requirements/dashboard-ux-redesign-brief.md) |
| Product setup and automatic preparation | [Simple onboarding and shared automation](product/simple-product-onboarding.md) |
| Framework and data boundaries | [System architecture](architecture/system-architecture.md), [Workspace access](security/workspace-access.md) |
| Find new companies | [Lead discovery](automation/lead-discovery.md) |
| Research an accepted company and determine industry | [Company research](automation/company-research.md) |
| Find LinkedIn and professional handles | [People profile search](automation/people-profile-search.md) |
| Review, score, match, draft and approve | [Lead preparation pipeline](automation/lead-preparation-pipeline.md) |
| Preparation reliability and separate email sending | [Reliability and SMTP](automation/preparation-reliability-and-sending.md) |
| API responsibilities and lifecycle | [Service map](api/service-map.md) |
| Development and release | [Local development](development/local-development.md), [GitHub and deployment](development/github-and-deployment.md), [Repository map](development/repository-map.md) |
| Earlier decisions, requirements and progress | [Historical archive](archive/README.md) |
| Intern assignments | [Poster and video API research brief](Intern%20Helper/creative-asset-provider-research.md) |
| Find a renamed document | [Old-to-new file map](file-map.md) |

Files use lowercase kebab-case names that describe their purpose. Dates identify progress snapshots, not arbitrary revision numbers. Keep current guides in the relevant purpose folder; put superseded requirements and dated snapshots in `archive/`. Add future changes to the current status and a dated change log rather than another ambiguous handoff file.

`knowledge/` is currently ignored by Git. These notes are local workspace context. Version-controlled implementation documentation lives in the repository's `docs/` and `integrations/n8n/` folders. Never put passwords, tokens or credential exports in knowledge documents.

Current priority: [MVP1 acceptance](automation/mvp1-acceptance.md).

- [Contact resolution and continuation](automation/contact-resolution.md) — source-backed manual contact entry and shared preparation resume.

- [LorrySystem document reference](product/lorrysystem-catalog-reference.md) — nine offerings and seven proposed ICPs from the 6 October Word document; application status recorded explicitly.

Current priority: validate the native research, contact review, scoring, matching and draft stages through pending human approval. The DEV dashboard/API and Python worker are deployed; the DietPi deployment helper now rebuilds and health-checks native services on future deployments. Keep legacy/n8n and production available until live preparation acceptance and rollback gates pass. See [native dashboard setup](../docs/native-dashboard-dev.md) and [native DEV cutover runbook](../docs/native-dev-cutover.md).

- [Native worker migration plan](architecture/native-worker-migration-plan.md) — stage implementation order, bounded two-product acceptance and executor cutover criteria.

- [Native preparation workers](architecture/native-preparation-workers.md) — implemented shared Python stages, human approval, source-backed contact continuation and provider reservation limits.

- [Frontend developer handoff](../docs/frontend-native-backend-handoff.md) — portable native frontend requirements, API contract, design references and backend dependencies; [OpenAPI snapshot](../docs/contracts/native-backend-openapi.json) accompanies it.

- [Native frontend backend support](architecture/native-frontend-backend-support.md) — BE-01–BE-06 implemented APIs and actual browser/worker integration, startup commands, migrations and frontend adapter handoff.

- [Native lead discovery and human acceptance](automation/native-lead-discovery.md) — Python scraping, Brave/xKiro, candidate inbox and explicit user acceptance. Supersedes automatic discovery acceptance; rollout status is recorded separately.

- [12 October rollout notes](status/2026-10-12-change-log.md) — native Compose wiring, local validation and remaining DEV prerequisites.
