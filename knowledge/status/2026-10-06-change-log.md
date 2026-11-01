# 6 October 2026 implementation changes

| Change | Result | Reference |
| --- | --- | --- |
| Product workspace foundation and automation adaptation | Private product teams, scoped records/catalogs, named service credentials and guarded workflow bindings replace the original single-product assumptions. | [Workspace guide](../../docs/PRODUCT_WORKSPACES.md), [n8n integration guide](../../integrations/n8n/README.md) |
| Automatic company research | Human acceptance creates a pending research job; DEV worker claims it, collects public evidence, uses xKiro and saves a complete/partial brief. | [PR #15](https://github.com/geekedctrl/lorrysystem-marketing-system/pull/15) |
| Professional research presentation | Executive summary, grouped findings, contact cards, source library, evidence expansion, gaps and research history. | [PR #16](https://github.com/geekedctrl/lorrysystem-marketing-system/pull/16), [Brief guide](../../docs/research-brief.md) |
| Company-linked people search | Bounded LinkedIn and professional social lookups; supported matches and conflicting identities kept separate. Existing n8n credentials reused. | [PR #17](https://github.com/geekedctrl/lorrysystem-marketing-system/pull/17), [Profile guide](../../docs/people-profile-search.md) |
| Company overview and industry | Overview moved above research, unnamed contact fallback fixed, missing industry populated from verified completed research and saved official evidence. Existing labels preserved and attribution audited. | [PR #18](https://github.com/geekedctrl/lorrysystem-marketing-system/pull/18) |

PR #17 and #18 are merged into develop. PR #18's branch and PR CI checks passed. DEV research extraction instructions and validation were published and verified active. The merged build's server rollout is a separate deployment check, not assumed from a successful branch test.

Validation recorded for the latest fix: 46 JavaScript tests, 7 research-presentation regressions, disposable API/dashboard checks for industry promotion and rejected unsupported evidence, workspace isolation, curated-value preservation, layout ordering and unnamed contacts, plus desktop/mobile browser verification. Earlier native n8n tests used mocked providers and the real disposable API across two workspaces; real DEV discovery/model connectivity was separately exercised during integration work.

All prior knowledge documents were retained under purpose-based names. Superseded plans and build handoffs now carry historical notices; their original completion claims remain historical evidence rather than current instructions.
