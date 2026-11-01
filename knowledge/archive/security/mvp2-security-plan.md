---
title: LorrySystem MVP2 Security Architecture
project: LorrySystem AI Marketing & Lead Generation
stage: MVP2
date: 2026-09-19
status: security-roadmap
---

> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem MVP2 Security Architecture

## 1. Objective

MVP2 moves the validated platform into a cloud production environment.

Security goal:

> Replace self-hosted assumptions and broadly shared secrets with stronger service identities, managed infrastructure, cloud monitoring, and controlled human access.

---

# 2. Cloud Network Architecture

Recommended:

```text
Internet
   ↓
Cloudflare
   ↓
Application Network
   ↓
Marketing API
   ↓
Private Database Network
   ↓
PostgreSQL / Managed PostgreSQL
```

PostgreSQL remains:

```text
private
not Internet reachable
```

If managed PostgreSQL is used:

```text
allow only Marketing API environment
require TLS where supported
```

---

# 3. Separate Machine Identities

Move from one shared service token to separate identities:

```text
n8n-research
n8n-marketing
dashboard-backend
admin-tools
```

Each gets its own credential.

Do not share one token across every service.

---

# 4. Scoped Authorization

Add scopes such as:

```text
leads:read
research:read
research:write
scoring:read
scoring:write
actions:read
actions:write
approvals:read
approvals:write
execution:write
```

Example:

```text
n8n-research
├── leads:read
├── research:read
└── research:write
```

Dashboard:

```text
approvals:read
approvals:write
```

Principle:

```text
each identity receives only required permissions
```

---

# 5. Stronger Token Model

Move beyond a single long-lived static secret toward one of:

```text
short-lived signed tokens
JWT service tokens
OAuth2 client credentials
managed service identity
```

Desired capabilities:

```text
expiration
rotation
revocation
audience validation
issuer validation
```

Do not add complexity until the cloud deployment is stable.

---

# 6. Human Authentication

For dashboard users:

```text
SSO / Cloudflare Access / identity provider
```

Requirements:

```text
MFA
named users
no shared accounts
session expiry
```

Human users must not reuse machine credentials.

---

# 7. Basic RBAC

Introduce simple roles:

```text
ADMIN
REVIEWER
MARKETING_OPERATOR
READ_ONLY
```

Example:

```text
ADMIN
→ full management

REVIEWER
→ view/approve/reject actions

MARKETING_OPERATOR
→ create/edit drafts and inspect leads

READ_ONLY
→ reporting only
```

Avoid over-engineering enterprise RBAC at this stage.

---

# 8. Managed Secrets

Move secrets from plain `.env` where practical into:

```text
cloud secret manager
Docker secrets
encrypted secret store
managed vault
```

Store:

```text
DB credentials
service tokens
AI provider keys
email provider credentials
social provider credentials
Cloudflare credentials
```

Requirements:

```text
central storage
restricted access
rotation
auditability
```

---

# 9. Database Security

Recommended cloud controls:

```text
private networking
TLS in transit
encrypted storage
automated backups
point-in-time recovery if available
separate migrator/runtime roles
```

Review:

```text
connection limits
idle sessions
statement timeouts
backup retention
```

---

# 10. WAF and Edge Protection

Enable edge controls such as:

```text
WAF
bot protection
IP reputation
rate limiting
request size limits
geo restrictions if useful
```

WAF does not replace application authentication.

---

# 11. Central Logging

Centralize:

```text
API logs
security logs
authentication failures
approval events
n8n errors
Cloudflare logs
database alerts
```

Logs should support:

```text
search
retention
alerts
incident investigation
```

---

# 12. Monitoring and Alerts

Alert on:

```text
repeated authentication failures
unusual API traffic
high 4xx / 5xx rates
database failures
approval anomalies
unexpected bulk exports
container restart loops
backup failures
```

---

# 13. API Abuse Controls

Introduce:

```text
per-service rate limits
request quotas
payload-size limits
timeout policies
replay protection where justified
```

Especially for:

```text
AI-heavy research endpoints
bulk lead operations
execution endpoints
```

---

# 14. Web Security Headers

For dashboard/web applications:

```text
HTTPS only
HSTS
Content-Security-Policy
X-Content-Type-Options
Referrer-Policy
frame restrictions
```

Cookies should use, where applicable:

```text
Secure
HttpOnly
SameSite
```

---

# 15. Backup and Recovery Security

Requirements:

```text
encrypted backups
off-server copy
automatic schedule
retention policy
restore test
restricted restore credentials
```

Document approximate:

```text
RPO
RTO
```

---

# 16. Definition of Done

```text
separate machine identities                    ✓
scoped authorization                           ✓
human MFA                                      ✓
basic roles                                    ✓
managed secret storage                         ✓
private cloud database                         ✓
TLS database connection                        ✓
WAF / edge protection                          ✓
centralized logs                               ✓
security alerts                                ✓
encrypted backups                              ✓
restore process tested                         ✓
```

---

# 17. Recommended Implementation Order

```text
1. Cloud migration
2. Private cloud networking
3. Separate machine identities
4. Authorization scopes
5. Human roles / MFA
6. Managed secrets
7. Managed/private database security
8. WAF / edge controls
9. Central logging
10. Monitoring / alerts
11. Encrypted backups
12. Restore testing
```
