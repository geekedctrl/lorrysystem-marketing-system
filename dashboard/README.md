# Marketing Dashboard

The dashboard now supports private product workspaces, authenticated accounts,
workspace switching, team invitations, role management and workspace catalogs.

See [Product workspace guide](../docs/PRODUCT_WORKSPACES.md) for deployment,
first-administrator setup and automation configuration. The historical MVP1 notes
below describe the original single-workspace build; API-key, reviewer identity and
ICP environment configuration have been replaced with account/workspace APIs.

# LorrySystem MVP1 Dashboard

Server-rendered FastAPI dashboard for the LorrySystem Marketing API.

## MVP1 architecture

```text
Browser
  |
  | HTTP/HTTPS
  v
Dashboard / BFF
  |
  | X-API-Key (server-side only)
  v
Marketing API
  |
  v
PostgreSQL
```

The dashboard joins `lorrysystem-api-net` only. It does **not** join
`lorrysystem-db-net` and contains no PostgreSQL credentials.

## Included

- Overview
- Lead list and basic filters
- Manual lead entry
  - choose or create company
  - choose or create/skip primary contact
  - choose ICP from server-side configuration
  - choose priority
- Lead detail
  - company/contact
  - research
  - score history
  - product matches
  - marketing actions
- Approval queue
- Approval detail using immutable `content_snapshot`
- Approve / Reject / Request Changes
- Marketing actions aggregation
- Safe system status
- Basic CSRF protection for forms
- Cloudflare Access reviewer identity support

## Important OpenAPI gap

The current Marketing API exposes no endpoint to list ICP profiles. Therefore
the three ICP IDs are configured **server-side** in `.env`:

```text
ICP_LOGISTICS_HAULAGE_ID=
ICP_PASSENGER_TRANSPORT_ID=
ICP_COMMERCIAL_ENTERPRISE_ID=
```

This avoids putting database UUIDs in browser JavaScript. A future
`GET /api/icp-profiles` endpoint can replace this configuration cleanly.

## Install

```bash
mkdir -p /opt/lorrysystem-dashboard
cd /opt/lorrysystem-dashboard
# Copy/extract this project here

cp .env.example .env
chmod 600 .env
```

Edit `.env` and set:

- `MARKETING_API_KEY`
- `DASHBOARD_SESSION_SECRET`
- the available ICP profile IDs

Then:

```bash
docker compose config
docker compose build
docker compose up -d
docker logs -f lorrysystem-dashboard
```

Local test:

```bash
curl -I http://127.0.0.1:8080/dashboard
```

Open locally at:

```text
http://SERVER-IP:8080
```

The Compose file binds to `127.0.0.1` by design. For remote use, place the
dashboard behind Cloudflare Tunnel + Access rather than changing the API
architecture.

## Cloudflare identity

When the dashboard is safely behind Cloudflare Access and direct origin access
is not available to untrusted clients, set:

```text
TRUST_CLOUDFLARE_IDENTITY=true
```

The dashboard will then use:

```text
Cf-Access-Authenticated-User-Email
```

as `decided_by` for approval decisions. Until then it uses
`DASHBOARD_REVIEWER_IDENTITY`.

## Security notes

- Marketing API key is never rendered into HTML.
- Browser never contacts Marketing API directly.
- Dashboard has no PostgreSQL network access.
- Form mutations use a session CSRF token.
- API error bodies are translated into user-facing messages.

This is MVP1 security, not full production RBAC.

## Lead Import Enhancement (v2)

This build adds:

- `/leads/import`
- Business-card upload with local Tesseract OCR
- Editable smart-autofill review before create
- CSV template download
- CSV upload + preview
- READY / DUPLICATE / NEEDS_REVIEW / INVALID classification
- Existing-company reuse
- Active lead duplicate detection
- Per-row CSV commit and summary
- 10 MB business-card image limit
- 5 MB / 5,000-row CSV limits

### Current Contact API compatibility note

The live Marketing API currently requires `ContactCreate.full_name`. Therefore a
CSV row or business card containing contact data but no contact name is held for
review rather than fabricating a name or silently discarding contact data.

Inspect the live `contacts.full_name` nullability and Contact model/schema before
creating migration `007`. If the database column is already nullable, only the
API schema/business validation may need changing. If the column is NOT NULL and
the locked import requirements must allow nameless contacts, migration `007`
will be required.

### Rebuild after upgrading from v1

```bash
cd /opt/lorrysystem-dashboard
docker compose build --no-cache dashboard
docker compose up -d dashboard
docker logs --tail 100 lorrysystem-dashboard
```

The Docker image now installs `tesseract-ocr`, Pillow, and pytesseract for local
business-card OCR. No OCR provider key is required for this MVP implementation.


## V2.1 Contact Nullability Dependency

CSV and business-card imports may create a Contact when meaningful contact data
exists even if `full_name` is blank. This requires Marketing API migration `007`
and corresponding Contact model/schema support for nullable `full_name`.

Do not deploy this V2.1 build before migration `007` is applied successfully.

## Dashboard UX

See [Dashboard UX redesign](../docs/dashboard-ux.md) for navigation, theme/interaction behavior, local browser validation and release boundaries.
