> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem AI Marketing & Lead Generation Agents
## Go / No-Go Decision and MVP1–MVP3 Roadmap

**Date:** 17 September 2026  
**Status:** Internal Management Draft  
**Recommendation:** **GO — phased development with controlled automation**

## Executive Decision

The project is technically feasible and should proceed in three controlled stages.

- **MVP1:** self-hosted proof of concept; prove the lead → research → score → approval → action → tracking loop.
- **MVP2:** migrate the validated system to cloud infrastructure and add multi-channel operations.
- **MVP3:** scale automation, analytics, video content and additional product lines.

**Operating objective:** keep Parimala's routine review workload below **1 hour/day or 3 hours/week** after stabilisation.

**Development fee:** RM1,000 per phase (RM3,000 total).  
**Monthly operating caps:** MVP1 USD50, MVP2 USD100, MVP3 USD150.

## Core Architecture

`Discover → Research → Match ICP → Score → Draft → Human Approval → Execute → Track → Analyse`

MVP1 runs on the existing Ubuntu VM using Docker with:

- n8n
- cloudflared
- PostgreSQL
- Marketing API
- Simple approval dashboard
- External AI/data/email APIs as required

## MVP1 — Proof of Concept

**Timeline:** 2–3 weeks  
**Monthly cap:** USD50  
**Development fee:** RM1,000

### Scope

- Existing self-hosted Ubuntu/Docker environment
- LorrySystem ICP implementation
- Controlled lead discovery and company research
- AI-assisted product fit and lead scoring
- Personalised email draft generation and low-volume approved tests
- Small competitor watchlist and recurring summary
- Social content drafts
- Approval dashboard: approve / edit / reject
- Basic activity reporting
- Backup/restore and cloud migration documentation

### Out of scope

- High-volume mass email
- Fully autonomous social commenting
- Unrestricted LinkedIn/member scraping
- Full multi-platform autonomous publishing
- AI video generation
- Multiple product workspaces
- High-availability cloud architecture

### GO-to-MVP2 gate

- End-to-end workflow functions
- Duplicate handling and source traceability work
- Approval queue usable by Parimala
- At least one controlled real workflow is validated
- Backup/restore is tested
- Operating spend remains within USD50/month

## MVP2 — Cloud Deployment & Multi-Channel Operations

**Timeline:** 3–4 weeks after MVP1 approval  
**Monthly cap:** USD100  
**Development fee:** RM1,000

### Scope

- Cloud migration
- Backups, monitoring and access controls
- Expanded lead enrichment and deduplication
- Email sequences, bounce/unsubscribe/suppression handling
- Expanded competitor intelligence
- Approved social publishing where official API access permits
- Engagement opportunity queue and comment drafts
- Content calendar
- Campaign analytics
- Additional LorrySystem ICPs

### GO-to-MVP3 gate

- Cloud deployment stable with tested restore
- Workflows require no manual data re-entry
- Approved multi-channel workflows operate where APIs permit
- Operator effort trends toward <3 hours/week
- Spend remains within USD100/month

## MVP3 — Scale, Video & Multi-Product Expansion

**Timeline:** 4–6 weeks after MVP2 approval  
**Monthly cap:** USD150  
**Development fee:** RM1,000

### Scope

- Multiple product workspaces
- AI video workflow with approval
- Advanced lead nurturing
- Campaign optimisation
- Broader social intelligence where permitted
- CRM/sales handoff
- Weekly executive reporting
- Role-based access and audit trail
- Increased low-risk automation while retaining approval for brand-sensitive actions

## Overall Timeline

Approximately **9–13 weeks** from approval, subject to management feedback and external API access.

## Roles

- **Research owner:** tools, APIs, data sources, competitor/platform research.
- **Sasi Anna / validation owner:** business validation, cost/scope validation, GO/NO-GO recommendation.
- **Karthik / development owner:** build, integration, testing, documentation and evolution.
- **Parimala / operator:** approval, review and quality feedback.
- **Management sponsor:** final phase approvals.

## Key Risks

- LinkedIn/social API restrictions
- Poor lead/data quality
- Brand risk from AI-generated content
- Email deliverability
- Scope creep
- Self-hosted POC reliability
- API cost changes

## Final Position

- **Overall project:** GO
- **MVP1:** GO
- **MVP2:** Conditional GO after MVP1 validation
- **MVP3:** Conditional GO after MVP2 cloud/multi-channel validation

**Management decision requested:** approve MVP1 under the USD50/month operating cap and RM1,000 development fee.

## Reference Notes

- n8n: https://docs.n8n.io/
- Cloudflare Tunnel: https://developers.cloudflare.com/tunnel/
- LinkedIn Community Management API: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/community-management-overview
- LinkedIn Comments API: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/comments-api

> Vendor/API allocations are planning envelopes, not quotations. Final provider selection and exact recurring cost should be confirmed during each phase.
