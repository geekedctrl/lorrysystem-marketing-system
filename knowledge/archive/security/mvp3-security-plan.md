---
title: LorrySystem MVP3 Security Architecture
project: LorrySystem AI Marketing & Lead Generation
stage: MVP3
date: 2026-09-19
status: security-roadmap
---

> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem MVP3 Security Architecture

## 1. Objective

MVP3 is the multi-product and scaling stage.

Security goal:

> Support more users, product workspaces, integrations, and automation while maintaining isolation, traceability, least privilege, and operational resilience.

---

# 2. Fine-Grained Authorization

Move beyond simple roles into permissions:

```text
workspace:read
workspace:admin
leads:read
leads:write
research:run
actions:create
actions:approve
actions:execute
reports:read
audit:read
```

Authorization decisions should consider:

```text
identity
workspace/product
resource
action
```

---

# 3. Workspace Isolation

If the platform expands to multiple products:

```text
LorrySystem
UNARVU
Future Product
```

users and services must not access another workspace's private data unless authorized.

Target:

```text
Workspace A identity
✕ Workspace B private data
```

Controls may include:

```text
workspace_id on business records
service-layer authorization
database row-isolation strategy
```

Do not rely only on frontend filtering.

---

# 4. Enterprise Identity / SSO

Recommended:

```text
OIDC / OAuth2
enterprise SSO
mandatory MFA
```

Potential providers may include:

```text
Microsoft Entra ID
Google Workspace
Okta
Cloudflare Access
```

No shared admin credentials.

---

# 5. Automated Secret Rotation

Automate rotation for:

```text
service tokens
database passwords
provider credentials
API keys where supported
```

Requirements:

```text
minimal downtime
audit trail
rollback procedure
```

---

# 6. Central Security Monitoring

Potential capabilities:

```text
SIEM
IDS / threat detection
Cloudflare security analytics
central audit store
anomaly detection
```

Monitor for:

```text
mass downloads
unusual approval behavior
credential abuse
unexpected provider calls
privilege changes
suspicious workspace access
```

---

# 7. Immutable Audit Trail

High-value operations should have durable audit history:

```text
logins
credential changes
lead modifications
research runs
score changes
product matching
marketing action changes
approval decisions
execution actions
administrative changes
```

Consider:

```text
append-only audit storage
tamper-resistant retention
```

for critical logs.

---

# 8. AI / Automation Least Privilege

Separate agent/service permissions.

Example:

```text
Research Agent
→ research permissions only

Marketing Draft Agent
→ actions:create

Approval User
→ approvals:write

Execution Workflow
→ execute approved actions only
```

Avoid giving one automation identity permission to:

```text
discover
research
score
draft
approve
execute
```

end-to-end.

---

# 9. Separation of Duties

For higher-risk operations:

```text
creator ≠ approver
```

Target flow:

```text
AI / operator creates draft
        ↓
human reviewer approves
        ↓
execution service sends
```

No single component controls the entire chain.

---

# 10. Data Protection

Evaluate:

```text
field-level encryption
PII classification
data-retention policy
secure deletion
export controls
backup key management
```

Potentially sensitive fields include:

```text
contact emails
phone numbers
company research
internal notes
approval metadata
```

---

# 11. Security Testing

Introduce recurring:

```text
dependency scanning
container image scanning
SAST
DAST
API security testing
penetration testing
backup restore testing
permission review
```

At minimum before major production releases.

---

# 12. Incident Response

Document response plans for:

```text
credential compromise
data breach
API compromise
database compromise
malicious automation
provider account compromise
backup compromise
```

Response flow:

```text
Detect
  ↓
Contain
  ↓
Rotate credentials
  ↓
Investigate
  ↓
Recover
  ↓
Review
```

---

# 13. Disaster Recovery

Define:

```text
RPO
RTO
backup locations
restore runbook
service recovery order
```

Suggested recovery order:

```text
Database
   ↓
Marketing API
   ↓
Authentication
   ↓
n8n
   ↓
Dashboard
```

---

# 14. Definition of Done

```text
fine-grained authorization                    ✓
workspace isolation                           ✓
enterprise SSO                                ✓
mandatory MFA                                 ✓
automated secret rotation                     ✓
central security monitoring                   ✓
tamper-resistant audit trail                  ✓
agent/service least privilege                 ✓
separation of duties                          ✓
data-retention policy                         ✓
regular security testing                      ✓
incident-response plan                        ✓
disaster-recovery runbook                     ✓
```

---

# 15. Recommended Implementation Order

```text
1. Fine-grained RBAC / permissions
2. Workspace isolation
3. Enterprise SSO
4. Automated secret rotation
5. SIEM / threat detection
6. Immutable audit trail
7. Agent least privilege
8. Separation of duties
9. Data protection / retention
10. Security scanning
11. Penetration testing
12. Incident response
13. Disaster recovery
```
