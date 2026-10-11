# Native Python backend rebuild

On 11 October 2026 the user requested rebuilding the platform and confirmed backend/workers first. The replacement lives in `backend/` with a separate Compose project and database. The existing deployed application and n8n remain operational until feature parity and cutover checks pass.

Milestone one implements authenticated workspaces, catalog/ICP storage, leads, a durable research queue, renewable leases, checkpoints, bounded retries and a native evidence-validating research worker. Separate database roles and forced workspace row-level policies protect business records. Its migrations are independent from the legacy database's migrations 009â€“014.

Research currently covers one homepage and stops for review. Discovery, contacts, qualification, matching, drafts, approvals, sending and the dashboard must still be implemented in the replacement. Existing provider credentials/data have not been migrated.

Ten PostgreSQL integration tests and a running restricted-role API/worker smoke test passed without live provider spending. Internal Docker health works; Windows host forwarding still needs verification. See [backend setup and scope](../backend/README.md).
