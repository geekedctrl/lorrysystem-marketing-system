> Latest requirement: discovered companies await explicit user acceptance. See [Native discovery](native-lead-discovery.md) for the new implementation and release status; older automatic-acceptance guidance below is historical.

# Lead discovery and candidate review

For administrator-activated products, [shared product automation](../product/simple-product-onboarding.md) supersedes the manual acceptance/contact/qualification steps described below. Existing unactivated workspaces retain the reviewed workflow. Both modes stop before sending.

Updated: 6 October 2026.

**Find Leads** requests a workspace-bound discovery run through the API and the published DEV dispatcher. The child loads current workspace metadata, verifies its named service credential and catalogs, searches and retrieves bounded public evidence, then creates reviewable candidates. It does not accept those candidates automatically.

Each product needs its own named Marketing API credential, reviewed ICPs/catalog, discovery query/context and discovery-memory registry. Preflight stops mismatched credentials or unsupported catalog context before paid requests. Memory lookup and writes enforce workspace ownership; company sites and directory listings use the appropriate canonical keys.

The customer chose not to use ZenRows. Public website retrieval follows the guarded fetch path with URL/DNS checks, redirect limits, robots checks and response limits. Browser rendering for difficult sites remains future work, not an activated fallback service.

Acceptance is a human operation. It creates the official company/lead as appropriate and a pending research job. Rejected or unrelated companies should remain out of the active lead pipeline.

See [the n8n package](../../integrations/n8n/README.md) for binding and dispatch setup, [dashboard dispatcher source](../../integrations/n8n/dashboard-discovery.js), [company research](company-research.md) for the next stage, and [archived discovery requirements](../archive/requirements/web-discovery-and-scraping.md) for original design intent.
