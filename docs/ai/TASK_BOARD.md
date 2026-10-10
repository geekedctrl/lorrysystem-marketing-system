# Task board

| ID | Scope | Priority | Role/owner | Branch | Dependencies | Acceptance / last verified result | Status |
|---|---|---|---|---|---|---|---|
| B-01 | Application, deployment, product audits and shared knowledge | P1 | lead + read-only specialists | codex/campaign-strategist | baseline | app9c0a3b0/deploycba785a, canonical docs and competitor gaps saved | DONE |
| B-02 | Mock strategist API and tenant persistence | P1 | backend, integrated by lead | codex/campaign-strategist | B-01 | api/app/campaign modules, migration015; 13 offline +27 DB checks passed | DONE |
| B-03 | Campaign proposal review UX | P1 | frontend, integrated by lead | codex/campaign-strategist | B-02 | dashboard templates/routes, 8 focused checks +62 actual HTTP/dashboard checks passed | DONE |
| B-04 | Regression, CI, PR and handoff | P1 | lead | codex/campaign-strategist | B-02,B-03 | 183 workspace, research/preparation/automation and n8n suites passed; PR pending | IN_PROGRESS |
| C-01 | Creative assets and budget reservation design | P2 | unassigned | future branch | B review | mock image adapter, tenant asset lifecycle, deterministic brochure, spend reservation tests; no live provider until authorized | BACKLOG |
| D-01 | Convert reviewed strategy to separately approved message actions | P2 | unassigned | future branch | B,C | immutable recipient/content approvals, existing SMTP controls, social drafts | BACKLOG |
| E-01 | Provider-neutral conversation CRM | P3 | unassigned | future branch | D | one official connector, human review, real outcome metrics | BACKLOG |
| F-01 | Optional video | P3 | unassigned | future branch | C,budget authorization | explicitly approved provider/cost experiment before enabling | BACKLOG |
