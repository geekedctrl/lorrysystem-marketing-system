# Product workspaces and private teams

One application serves multiple products. Each product workspace owns its
company/contact records, candidates, leads, research, scores, catalog, ICPs,
marketing actions, approval queue and activity history. LorrySystem is the first
workspace; TMS, GPS and its other offerings stay inside that workspace's catalog.

## Access model

Users sign in with email/password. Passwords are salted PBKDF2-SHA256 hashes;
revocable, 12-hour session tokens are stored as SHA256 hashes in the API database.
The dashboard uses an HttpOnly signed session cookie, forwards the user's token
server-side and checks current memberships on every request. Roles supplied by
the browser are never trusted. Workspace membership changes take effect on the
next request, including existing sessions.

| Workspace role | Read | Lead/research/draft operations | Approval decisions | Team/configuration |
| --- | --- | --- | --- | --- |
| Viewer | Yes | No | No | No |
| Operator | Yes | Yes | No | No |
| Reviewer | Yes | No | Yes | No |
| Administrator | Yes | Yes | Yes | Yes |
| Automation credential | Yes | Yes | No | No |

A platform administrator can create workspaces. That permission does not
implicitly grant access to existing workspaces. A workspace creator receives an
explicit Administrator membership and can invite the product's team. Removing
the final Administrator is rejected. Workspace administrators cannot reset an
existing user's global account password through an invitation.

## Data isolation

Migration `009` adds workspace ownership to 14 business tables and assigns all
existing records to LorrySystem (`00000000-0000-0000-0000-000000000001`). IDs,
history and lifecycle states are retained. Domain/email/catalog-code uniqueness
is scoped to a workspace, so private teams can independently hold the same
prospect. Composite foreign keys prevent relationships across workspaces.

Business sessions use `SET LOCAL ROLE marketing_workspace_runtime` and a
transaction-local workspace setting. That role is neither superuser nor RLS
bypass and has no access to account, invitation or credential tables. PostgreSQL
row-level policies filter reads and reject foreign-workspace writes, including
raw SQL and queue claims. Each new transaction reinstalls its role/context;
pooled connections do not retain the previous workspace setting.

Account and membership operations use a separate control session with explicit
authorization checks. Database administration credentials remain privileged and
must remain available only to the API/server administrator.

CSV preview files are bound to the session hash and workspace. Switching
workspaces or signing in with another session cannot export or commit a previous
preview. Actor names in action, approval and closure audits come from the
authenticated principal, rather than submitted form values.

## Deployment and first administrator

The API entrypoint now runs `alembic upgrade head` before starting Uvicorn.
An unsuccessful migration stops the API rather than serving against an old
schema. A PostgreSQL session advisory lock serializes startup and explicit
operator/CI migration commands. Compose keeps the dashboard dependent on API health.

Before merging/deploying this database change, take a verified PostgreSQL backup
through the existing server backup procedure. Migration `009` requires database
ownership and permission to create/grant the restricted runtime role. Keep the
migration directory mounted as defined in `docker-compose.yml`.

After the DEV deployment, create the first account interactively on the server:

```bash
docker exec -it lorrysystem-dev-marketing-api \
  python -m app.manage bootstrap-admin --email YOUR_ADMIN_EMAIL
```

The command prompts for a password of at least 12 characters and only works when
no user accounts exist. No default user or password is shipped. Subsequent
accounts join using 48-hour invitation links from **Workspaces & team**; links
must be shared by the administrator. The app does not send invitation emails.
Existing account holders enter their current password when accepting a link.

Configure the dashboard's existing `dashboard/.env`:

```env
DASHBOARD_SECURE_COOKIES=true
DASHBOARD_PUBLIC_URL=https://dashboard-dev.obsidian.cam
```

Use secure cookies for the public HTTPS endpoint; use `false` only for local HTTP
testing. `DASHBOARD_PUBLIC_URL` makes invitation links absolute. Without it,
the UI generates a relative link. The existing session secret remains required.
Dashboard API-key, reviewer identity and ICP UUID environment variables are no
longer used for user operations; account identity and ICPs come from the API.

Server administrators can recover an account without logging its password:

```bash
docker exec -it lorrysystem-dev-marketing-api \
  python -m app.manage reset-password --email EXISTING_ACCOUNT_EMAIL
```

A password reset invalidates all of that user's login sessions. Users can also
change their own password from Workspaces & team.

## Automation and n8n transition

Existing `MARKETING_API_KEY` remains restricted to LorrySystem only. Supplying
another workspace ID with it is denied. It cannot manage teams or approve an
action, or accept/reject discovered candidates. Synthetic n8n workflows that previously auto-approved actions must use
a real human approval step instead.

For each new workspace:

1. Add its product offerings and ICPs in Workspaces & team.
2. Create an automation credential there and store it in that workflow's n8n
   Header Auth credential (`X-API-Key`). The token is displayed only once.
3. Fetch `GET /api/workspace-context` to obtain workspace identity, brand settings,
   product catalog and qualification rules. Use these when constructing discovery,
   research and scoring prompts.
4. Prefix discovery-memory keys with workspace ID, or use a separate n8n Data
   Table for each workspace. Never reuse the LorrySystem novelty registry globally.
5. Configure separate sender/social credentials and schedules for each product.
6. Route approval decisions through a workspace Reviewer or Administrator account.

Research queue claims (`POST /api/research/claim`) are automatically restricted to
the credential's workspace. Credential revocation is checked on every request.
After moving LorrySystem workflows to named workspace credentials, set
`ENABLE_LEGACY_API_KEY=false` in the root environment and recreate the API.

Live n8n workflows and its Data Tables are outside this Git repository. This
change supplies the API/configuration/access foundation; it does not modify or
provision those live workflows. Product onboarding still requires the n8n steps
above. The monthly budget setting is configuration for automation; this release
does not enforce provider-spend caps or calculate invoices. Campaign scheduling,
provider integration and richer campaign analytics remain their roadmap stages.

## Validation

GitHub CI runs the workspace integration suite, the existing business-card/CSV
regression with an authenticated test account, and a separate migration exercise.
Tests run only with `APP_ENV=ci` or `workspace-test` for the database-mutating
workspace suites. Never run them against customer data.

The disposable local environment in `compose.workspace-test.yml` uses a named
test volume and ports 8011/8091; it never mounts the existing `data/` directory.
Supply randomly generated `WORKSPACE_TEST_DB_PASSWORD`, `WORKSPACE_TEST_API_KEY`
and `WORKSPACE_TEST_SESSION_SECRET` via an ignored env file.

The regression covers two private teams, overlapping prospect data, cross-team
record access and relationships, role restrictions, human approvals, queue claims,
credential revocation, invitation reuse, password/session revocation, browser
CSRF, dynamic ICPs and workspace-bound CSV imports. The migration suite verifies
legacy backfill, single-workspace downgrade and atomic refusal of a downgrade
after a second workspace exists.

Historic `validate_full_stack_007/008.py` scripts describe previous schema and
authentication snapshots. They are not the acceptance suite for revision `009`.
Use the current CI workspace suites for this release.

## Revised MVP sequencing

Workspace ownership, accounts, restricted teams and configurable product/ICP
catalogs move into the current foundation. MVP1 still validates the real marketing
loop with LorrySystem. MVP2's cloud/channel work uses that foundation. MVP3 expands
product onboarding, automation and reporting instead of introducing data isolation
for the first time. Separate teams' data remains private by default; cross-workspace
sharing is not enabled.
