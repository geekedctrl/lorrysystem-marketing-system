# Native Python backend rebuild

On 11 October 2026 the user requested rebuilding the platform and confirmed backend/workers first. The replacement lives in `backend/` with a separate Compose project and database. The existing deployed application and n8n remain operational until feature parity and cutover checks pass.

The foundation implements authenticated workspaces, catalog/ICP storage, leads, a durable queue, renewable leases, checkpoints and bounded retries. The next implementation adds native product setup, discovery, deeper research, professional contacts, scoring, product matching, drafts and immutable human approval snapshots. Separate database roles and forced workspace row-level policies protect business records. Replacement migrations are independent from the legacy database.

Eligible native preparation advances automatically to pending human approval; sending is absent. Manual homepage research remains a separate control. Current dashboard/data/provider credentials have not been migrated. The deployed application continues using n8n until cutover acceptance. See [native preparation workers](native-preparation-workers.md).

Thirty PostgreSQL integration tests and a running restricted-role API/worker smoke test passed without live provider spending. Synthetic acceptance includes three companies per product across transport and accounting catalogs. Real-provider quality and sending remain unverified. Internal Docker health works; Windows host forwarding still needs verification. See [backend setup and scope](../backend/README.md).
