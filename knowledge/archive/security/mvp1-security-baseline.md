---
title: LorrySystem MVP1 Security Architecture
project: LorrySystem AI Marketing & Lead Generation
stage: MVP1
date: 2026-09-19
status: security-hardening
---

> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem MVP1 Security Architecture

## 1. Objective

MVP1 security goal:

> Prevent unauthorized users or services from reaching business API endpoints or directly accessing PostgreSQL.

Current stage:

```text
Business APIs complete
        ↓
MVP1 Security Hardening
        ↓
Security Validation
        ↓
n8n Integration
```

The Marketing API remains the security choke point between clients/automation and business data.

---

# 2. Architecture

```text
n8n / Dashboard / Future Clients
                │
                │ HTTP / JSON
                ▼
         Marketing API
                │
                │ SQLAlchemy / psycopg
                ▼
           PostgreSQL
```

Rules:

```text
n8n       ✕ PostgreSQL
Dashboard ✕ PostgreSQL
Internet  ✕ PostgreSQL

Marketing API ✓ PostgreSQL
```

---

# 3. Central Bearer Authentication

Protect all business endpoints under:

```text
/api/*
```

using centralized Bearer-token authentication.

Example:

```http
Authorization: Bearer <service-token>
```

Expected behavior:

```text
No token      → 401 Unauthorized
Invalid token → 401 Unauthorized
Valid token   → request continues
```

Authentication should happen once at the API boundary.

```text
Incoming Request
      ↓
Authentication Layer
      ↓
Valid?
  ┌───┴────┐
  │        │
 NO       YES
  │        │
401     Router
           ↓
        Service
           ↓
        Database
```

Do not duplicate Bearer authentication manually in every router.

---

# 4. Endpoint Protection

Require authentication for:

```text
/api/companies/*
/api/contacts/*
/api/leads/*
/api/research/*
/api/scoring/*
/api/products/*
/api/product-matches/*
/api/actions/*
/api/approvals/*
```

Potentially public:

```text
GET /health
```

Recommended protected:

```text
GET /health/db
```

because it reveals internal database reachability.

---

# 5. n8n Service Credential

n8n should use a dedicated machine/service credential.

```text
n8n
 │
 │ Authorization: Bearer <n8n-service-token>
 ▼
Marketing API
```

Requirements:

```text
long random token
stored in n8n credential/secret storage
stored securely on API side
never committed to Git
never logged
rotatable
```

Do not embed the token directly into exported workflow JSON if avoidable.

---

# 6. Database Least Privilege

Do not rebuild PostgreSQL.

Keep:

```text
existing database
existing tables
existing data
migrations 001–006
existing constraints
```

Add proper database roles:

```text
postgres/admin
    └── administration only

marketing_migrator
    └── Alembic/schema changes

marketing_runtime
    └── FastAPI runtime access
```

`marketing_runtime` should NOT have:

```text
SUPERUSER
CREATEDB
CREATEROLE
ALTER SYSTEM
DROP DATABASE
```

Give it only the minimum application privileges required, typically:

```text
SELECT
INSERT
UPDATE
DELETE
```

on application tables and required sequences.

---

# 7. PostgreSQL Isolation

Preserve:

```text
PostgreSQL port 5432 NOT published
```

Correct:

```text
5432/tcp
```

Incorrect:

```text
0.0.0.0:5432->5432/tcp
```

Network goal:

```text
marketing-api
├── lorrysystem-api-net
└── lorrysystem-db-net

postgres
└── lorrysystem-db-net

n8n
└── API-facing network only
```

Rules:

```text
n8n         ✕ DB network
cloudflared ✕ DB network
dashboard   ✕ DB network
```

Only Marketing API should reach PostgreSQL.

---

# 8. Cloudflare Access

For human/admin access:

```text
Internet
   ↓
Cloudflare Access
   ↓
Cloudflare Tunnel
   ↓
Marketing API
```

Use:

```text
approved identity
+
MFA
```

Cloudflare Access is an additional defense layer, not a replacement for API authentication.

Target:

```text
Cloudflare Access
        +
Bearer Authentication
```

---

# 9. API Documentation Protection

Development may keep:

```text
/docs
/redoc
/openapi.json
```

enabled.

Production should:

```text
disable them
or
require authentication
```

Recommended:

```text
APP_ENV=development
→ docs enabled

APP_ENV=production
→ docs protected/disabled
```

---

# 10. CORS and Host Restrictions

Use strict CORS.

Avoid:

```text
Access-Control-Allow-Origin: *
```

for authenticated production APIs.

Allow only known dashboard/frontend origins.

Also consider trusted-host validation.

---

# 11. Rate Limiting

Add basic API rate limiting to reduce:

```text
brute-force attempts
credential abuse
accidental workflow loops
denial-of-service risk
```

Rate-limit categories may include:

```text
authentication failures
read endpoints
write endpoints
approval endpoints
```

Return:

```text
429 Too Many Requests
```

Do not throttle legitimate n8n workflows so aggressively that normal operation breaks.

---

# 12. Security Audit Logging

Keep existing business events and add security-focused logging:

```text
auth_failed
auth_success
forbidden_operation
rate_limit_triggered
invalid_token
```

Log:

```text
timestamp
service/client identity
request path
result
request ID
```

Never log:

```text
Bearer tokens
passwords
API secrets
database passwords
```

---

# 13. Secret Handling

Secrets include:

```text
PostgreSQL passwords
Bearer tokens
Cloudflare token
future provider API keys
```

Requirements:

```text
never commit real .env
restrict file permissions
do not print secrets in logs
do not paste production secrets into docs
rotate secrets if exposed
```

Suggested:

```bash
chmod 600 .env
```

---

# 14. Container Hardening

Where compatible:

```text
run app as non-root
drop unnecessary Linux capabilities
do not mount Docker socket into API
do not use privileged containers
pin image versions where practical
use read-only filesystem where practical
```

Test each change before keeping it.

---

# 15. Backup Security

Backups may contain the full marketing dataset.

Requirements:

```text
restricted file permissions
not publicly served
not committed to Git
stored outside application web root
restore tested
```

Prefer encryption for off-host backups.

---

# 16. Security Validation Checklist

MVP1 Security is complete when:

```text
/api/* rejects missing token                     ✓
/api/* rejects invalid token                     ✓
valid n8n token succeeds                         ✓
protected health endpoint works                  ✓
docs protected/disabled in production            ✓

PostgreSQL port not published                    ✓
runtime DB user is non-superuser                 ✓
runtime DB user cannot create/drop DB            ✓
n8n cannot reach PostgreSQL directly             ✓

Cloudflare Access configured for human access    ✓
CORS restricted                                  ✓
rate limiting active                             ✓

auth failures logged                             ✓
secrets absent from logs                         ✓
.env protected                                   ✓

security regression tests pass                   ✓
```

---

# 17. Definition of Done

```text
Central Bearer Authentication       ✓
Private PostgreSQL                  ✓
Least-Privilege Runtime DB User     ✓
Cloudflare Access                   ✓
Protected API Docs                  ✓
CORS / Host Restrictions            ✓
Basic Rate Limiting                 ✓
Security Audit Logging              ✓
Secret Hygiene                      ✓
Basic Container Hardening           ✓
Backup Protection                   ✓
```

After this:

```text
n8n Integration
```

may begin.

---

# 18. Recommended Implementation Order

```text
1. Central Bearer Authentication
2. Protect /api/*
3. Create n8n service credential
4. Create least-privilege DB runtime user
5. Preserve DB network isolation
6. Configure Cloudflare Access
7. Protect API docs
8. Restrict CORS / hosts
9. Add rate limiting
10. Add security audit logs
11. Harden secrets
12. Harden container
13. Validate security
14. Start n8n integration
```
