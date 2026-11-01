# Workspace access and credential boundaries

Updated: 6 October 2026.

Users authenticate with email/password and receive revocable sessions. Workspace membership determines access; platform administration alone does not grant membership in every product. Browser-submitted role or actor values do not authorize actions.

| Role | Main permission |
| --- | --- |
| Viewer | Read workspace records. |
| Operator | Lead, research and draft operations. |
| Reviewer | Approval decisions. |
| Administrator | Workspace operations, approvals, team/configuration. |
| Named service credential | Workspace automation operations; no human approval decisions or candidate acceptance. |

Business records carry workspace ownership. The API uses a restricted PostgreSQL runtime role, transaction-local workspace setting, row-level policies and workspace-consistent relationships. Discovery/research preflight additionally checks the named credential, expected workspace and current ICP/catalog context before paid work.

Create each product's automation credential in Workspaces & team and store it as n8n Header Auth with header `X-API-Key`. Brave uses `X-Subscription-Token`; xKiro uses `x-api-key`. Bindings and exported workflows contain credential IDs/names, not secret values. Product-specific sender credentials must be mapped before later outreach automation is activated.

Do not use the legacy global LorrySystem key for the adapted workflows. Disable legacy access after the relevant migration checks in the workspace deployment guide. Monthly budget settings are configuration, not implemented provider-spend enforcement.

See [the workspace guide](../../docs/PRODUCT_WORKSPACES.md) for bootstrap, migration and detailed access behavior, and [n8n binding instructions](../../integrations/n8n/README.md) for credential setup. Earlier single-product security plans are retained in [the archive](../archive/README.md).
