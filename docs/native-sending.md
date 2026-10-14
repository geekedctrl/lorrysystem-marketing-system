# Native controlled sending

Implemented locally on 15 October 2026. This is Python sending parity for the independent native backend. It does not authorize a real message, enable DEV ownership, or change the existing n8n executor.

Migration `009_native_sending` adds workspace-scoped encrypted SMTP connections, immutable delivery snapshots, a distinct send-approval state, suppressions and a transactional delivery outbox. The API never returns stored passwords. `SENDER_CREDENTIAL_ENCRYPTION_KEY` is a stable Fernet key shared by the native API and worker and must be backed up with deployment secrets.

An approved preparation draft still does not send. An ADMIN or OPERATOR creates a delivery from an approved, current EMAIL approval and a verified sender. This freezes recipient, subject, body, approval version and context. A second explicit `approve-send` call creates the outbox attempt in the same transaction. Duplicate create and approval requests return the existing record.

The worker claims ready attempts with `FOR UPDATE SKIP LOCKED`. Known failures before SMTP DATA may be retried explicitly, with a maximum of three attempts. A disconnect after DATA, an unexpected transport failure, or worker lease expiry becomes `UNCERTAIN` and cannot be retried because the provider may already have accepted the message. SMTP uses public-address pinning, TLS on 465 or STARTTLS on 587, and a stable Message-ID. `ACCEPTED` means SMTP acceptance only.

API surface under `/workspaces/{workspace_id}`:

- `GET/POST /senders`, `PUT /senders/{id}`, `POST /senders/{id}/verify`
- `POST /deliveries`, `POST /deliveries/{id}/approve-send`, `POST /deliveries/{id}/retry`, `GET /deliveries/{id}`
- `POST /email-suppressions`

Synthetic PostgreSQL acceptance covers encrypted credential use, redacted reads, separate send approval, idempotent delivery creation, transactional outbox creation, suppression, stale context, accepted handoff, known failure retry, uncertain handoff duplicate prevention and terminated-worker recovery. No SMTP server or recipient was contacted.

The native dashboard now exposes redacted sender setup and verification, suppressions, delivery creation from an approved email, separate send approval, delivery history and bounded retry controls. Its BFF enforces the same workspace role matrix and route allowlist. Synthetic browser acceptance verifies the complete content-approval to queued-outbox journey without contacting SMTP.

Remaining release work: controlled test-inbox verification with explicit approval, DEV executor ownership/cutover, migration reconciliation and the 14-day rollback window. Production deployment and real outbound sending require separate human approval.
