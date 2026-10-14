# Native DEV cutover review checklist

This checklist is a review artifact. Completing it does not activate ownership or deploy services.

## Before migration

- [ ] Native PostgreSQL is disposable or backed up and Alembic is at `010_executor_ownership`.
- [ ] Legacy PostgreSQL access uses a read-only account.
- [ ] Native migration credentials and encryption keys are present privately.
- [ ] `OWNERSHIP_CUTOVER_READY` remains `false` until reconciliation and legacy preflight checks pass.
- [ ] All four capabilities report `N8N / ACTIVE`.
- [ ] Provider keys are synthetic or absent; SMTP transport is a test stub.

## Migration evidence

- [ ] Run `migration export` and retain the immutable JSON artifact.
- [ ] Run `migration dry-run`; review pending legacy jobs and schema differences.
- [ ] Run `migration apply` only after the dry-run review.
- [ ] Run `migration reconcile`; users, workspaces, memberships, catalog, leads, preparation runs, approvals, identifiers, and status distributions match.
- [ ] Sender credentials, if imported, are re-encrypted, disabled, and unverified.
- [ ] No pending legacy send is represented as a ready native outbox attempt.

## Synthetic ownership sequence

For each capability in order: `SETUP`, `DISCOVERY`, `PREPARATION`, `SENDING`:

1. Confirm native claims are rejected while ownership is `N8N / ACTIVE`.
2. Drain the capability and confirm new legacy claims stop.
3. Wait for active leases to reach zero; record the operations view.
4. Activate Python and prove one native claim completes once.
5. Roll back within the deadline and prove Python claims stop before n8n resumes.

No provider, SMTP, or outbound network traffic is permitted during this sequence.

## Release gates

- [ ] Native API, worker, dashboard, and health checks are green.
- [ ] Legacy API and generated n8n preflight tests are green.
- [ ] PostgreSQL ownership, lease, migration, and fail-closed tests are green.
- [ ] Operations view shows ownership, leases, migration status, and differences.
- [ ] A reviewer records the decision and rollback deadline for each capability.
- [ ] DEV deployment is separately approved; production and real-provider activity remain out of scope.
