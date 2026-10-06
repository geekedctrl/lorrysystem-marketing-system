# Workspace-aware n8n automation

This package adapts exported n8n workflows offline. It does not change a running
n8n instance or provision sender accounts. Workflow exports contain credential
references only; API keys and provider secrets stay in n8n credentials.

## Reviewed lead stages

The [lead preparation guide](../../docs/lead-preparation-pipeline.md) covers
**Research → Contact review → Qualification/scoring → Product matching → Outreach
draft → Approval**. `pipeline-workflows.js` generates a shared stage child and a
workspace-bound queue worker; `pipeline-runtime.js` supplies their strict
context/evidence/output checks. Generate from the same workspace API/custom-model
credential references used for research, with `llm.max_tokens: 6000`.

Human contact confirmation and qualification remain dashboard decisions. The
worker handles SCORING, MATCHING and DRAFTING, creates pending human approval,
and stops there. No sender account or sending node is part of this pair. Publish
the child first, then its worker. The worker waits for `/api/pipeline/health`
version 1 until the application update and Alembic migration **011** are deployed.
Exports remain inactive; publishing to a live n8n instance is a separate action.

Run `node --test integrations/n8n/pipeline.test.js` alongside the existing runtime
tests. `api/scripts/validate_lead_pipeline.py` verifies the complete stage lifecycle
in disposable environments. See the guide for routes, rubric, roles, transaction
rules, stale-context protection, deployment and current limitations.

The API must first be deployed with the versioned `automation` metadata on
`GET /api/workspace-context`. No database migration is needed for this addition.

## Start with a preflight

Import `workspace-preflight.json` into DEV n8n as an inactive workflow. It contains:

```text
Manual Trigger → Workspace Configuration → Load Workspace Context → Workspace Guard
```

1. Create a named automation credential from the dashboard's Workspaces & team.
2. In n8n create **Header Auth**, with name `X-API-Key` and the token as its value.
   Select it on **Load Workspace Context**. Do not enter the token in a Code node,
   expression, input payload, or ordinary request header parameter.
3. Edit the **Workspace Configuration** Code node's constant: set `workspace_id`
   and the internal `api_base_url` reachable from n8n. Set the matching
   `X-Workspace-ID` header on **Load Workspace Context**.
4. Run manually. The guard must return the configured workspace, its active ICPs,
   product catalog, settings, ID maps and current discovery prompt.
5. Repeat for another product. Deliberately select the first product's credential
   in the second workflow: the request must fail before downstream nodes execute.

The guard rejects the old global LorrySystem key, user-session credentials,
unsupported contract versions and empty discovery catalogs. Configure named
credentials for LorrySystem as well. `require_catalog: false` is available for
non-discovery health checks; do not use it to activate discovery without ICPs.

## Adapt the supplied Level 1 / 1.1 discovery workflow

`workspace-discovery.template.json` is the sanitized, product-neutral adaptation
of the supplied 59-node discovery export. Generate an importable **62-node inactive
copy** using `adapt-discovery.js`; the template itself is not ready to import.

```bash
node integrations/n8n/adapt-discovery.js \
  tmp/discovery-binding.json tmp/discovery-workspace.json
```

Start the binding from `discovery-binding.example.json`. Select the workspace's
named Marketing API credential, a dedicated registry table, and Brave/custom-model
credential references from the target n8n instance. Credential IDs from another
instance are not portable. Only `id` and `name` belong in this file, never tokens.
The example uses DEV's internal API origin; the API has no public DEV hostname.

The `llm` binding selects an HTTPS base URL, model, provider label, output-token
limit and n8n Header Auth credential reference. The default is xKiro at
`https://api.xkiro.com/v1`, with `mistralai/mistral-large-2512`. **Custom Model
Structured Extraction** sends a non-streaming JSON Chat Completions request to
`/chat/completions`, with workspace catalog instructions and public company
evidence. It uses `response_format: {type: "json_object"}`, temperature 0 and a
default `max_tokens` ceiling of 2000. The response validator reads
`choices[0].message.content`, requires `finish_reason: "stop"`, and checks the JSON
and workspace ICP code. Truncated responses, provider/transport failures and
invalid JSON follow the existing registry failure/retry path without creating
candidates. Provider/model attribution and valid token-usage counters are retained;
provider error bodies are not copied into candidate or registry results.

For xKiro, create or select the n8n **Header Auth** credential named
**xKiro DEV model API**, with header name `x-api-key` and the key as its value.
Select that credential in **Custom Model Structured Extraction**. Store the key
in n8n's credential store. The workflow binding holds only the credential ID/name,
base URL and model; xKiro variables are not needed in `.env` or the Marketing API
container. No OpenAI credential or SDK is required. Redirects are disabled on
model requests. Other compatible
gateways can use an appropriate Header Auth credential, such as `Authorization`
with a `Bearer …` value, without changing the extraction pipeline.

Provider contract: [xKiro Chat Completions](https://docs.xkiro.com/api/chat-completions/)
and [authentication](https://docs.xkiro.com/guides/authentication/).

The adapter preserves retry windows, existing-candidate/active-lead handling,
website-credit contact checks, source evidence and the confidence thresholds.
It loads current catalogs before search, removes seed ICP UUIDs and the fixed
logistics classifier, resolves AI ICP codes through the current catalog, and
verifies the candidate's ICP plus authenticated workspace context. A null ICP
means no fit and follows the rejection path. Unknown codes fail extraction.
Dashboard rendering and human review are verified separately using a user login.

All 12 memory nodes use the dedicated table and write workspace ownership. Each
lookup/update checks both ownership and the scoped canonical URL key. Direct
company sites remain domain-scoped through their root canonical URL; directory
listings remain page-scoped. Existing and final rows must pass ownership checks.

Configure each product's discovery query, country, directory domains and optional
literal relevance keywords in its binding. Empty keywords defer relevance to the
workspace ICP evaluation, allowing products outside logistics. The example keeps
LorrySystem's query only as an example binding. Scanning is bounded to at most 200
raw results, with at most 20 results per Brave page. `target_new_companies` limits
new discoveries; due retries also consume fetch/AI calls. These are run limits,
not enforcement of the workspace's monthly spend setting. Run one discovery at
a time per workspace. Public fetch redirects require separate validation.

For DEV setup, `.env.n8n-dev` stays ignored. `MARKETING_WORKSPACE_API_KEY` is created
in the dashboard: select the product, open **Workspaces & team → Automation
credentials**, enter a name and select **Create credential**. Copy the token shown
once. Use it in n8n Header Auth with header name `X-API-Key`. Brave uses Header Auth
with `X-Subscription-Token`. xKiro uses Header Auth with `x-api-key`.

The DEV copy created on 2026-10-06 is **LorrySystem DEV - Workspace Lead Discovery**,
with named Marketing API/Brave/xKiro credentials and a dedicated registry
initially containing 34 migrated historical rows. Statuses, IDs, counters and retry dates
were verified against the original. The original table and workflows were left
unchanged. Custom-model auth is bound to xKiro using the supplied key. A small
synthetic JSON request passed both directly and through real DEV n8n, using the
requested Mistral model; the remote check reported 19 total tokens. A subsequent
live discovery run saved four new candidates with verified source evidence.
The child and dashboard dispatcher are now published for dashboard-requested
runs. Live preflight confirmed 3 ICPs and
6 offerings, and one public Brave result verified the provider key. Temporary
connectivity-check workflows and their authentication credentials were removed.

## Bind an existing workflow

Export the original workflow and keep it under an ignored directory such as
`tmp/`. Review it for inline secrets. Copy `binding.example.json` there and edit
its identifiers and node names. The binding contains no token values.

```bash
node integrations/n8n/bind-workflow.js bind \
  tmp/discovery-original.json tmp/lorry-binding.json tmp/discovery-lorry.json
```

The tool inserts preflight between the trigger and the original first nodes. It
preserves JSON/binary input and item pairing, changes explicitly listed API nodes
to the selected Header Auth credential and workspace header, binds every listed
registry node to a dedicated workspace Data Table, and selects the declared sender
credentials. It clears pinned data and static workflow memory, strips workflow
identity, and leaves the output inactive. It never overwrites an existing file.

Binding fields:

| Field | Meaning |
| --- | --- |
| `workspace_id` | Expected immutable API workspace UUID |
| `api_base_url` | Fixed API HTTP(S) origin; no secrets or expressions |
| `api_credential` | Named n8n Header Auth credential `id` and `name` |
| `trigger_nodes` | The workflow's single trigger node name |
| `api_nodes` | HTTP Request node names mapped to `/api/...` business paths |
| `registry_table_id` | Dedicated n8n Data Table ID for this workspace |
| `registry_nodes` | Every registry Data Table row node name |
| `sender_nodes` | Sender node name → credential type and credential reference |
| `shared_nodes` | Explicitly reviewed shared search/AI credential nodes |

Dynamic record paths can use existing expressions, for example
`/api/research/{{ $json.research_id }}/complete`. API nodes must use HTTP Request
version 4. They stop on failure and do not forward credentials on redirects.

Unclassified credential, Data Table and common sender nodes cause an error.
Sub-workflow calls and Execute Command nodes require manual adaptation; the tool
rejects them. Split workflows with multiple triggers into separately bound entry
points. This avoids accidentally retaining a path that skips preflight.

### Replace old context in prompts and payloads

Binding credentials alone does not rewrite arbitrary Code nodes or AI prompts.
Before activating an adapted export, replace hardcoded product/ICP assumptions:

```javascript
const context = $('Workspace Guard').first().json.workspace_context;
// Use this as the system prompt in the discovery AI node:
const prompt = $('Workspace Guard').first().json.workspace_prompt;
```

For research, scoring, matching and drafting, put the functions from
`workspace-runtime.js` above the Code node's own code, then call
`workspacePrompt(context, 'research')`, `'scoring'`, `'matching'` or `'drafting'`.
The helpers do not make an AI call. Your existing AI node uses the returned prompt
and source evidence. Context is fetched on every run so catalog/settings changes
are reflected on the next execution.

Resolve an AI-selected code to the current workspace's UUID before Candidate API:

```javascript
// Put workspace-runtime.js functions above this code.
const context = $('Workspace Guard').first().json.workspace_context;
return $input.all().map((item, index) => {
  const candidate = { ...item.json.candidate,
    suggested_icp_profile_id: icpId(context, item.json.suggested_icp) };
  assertCandidate(context, candidate);
  return { json: { ...item.json, candidate }, pairedItem: { item: index } };
});
```

Choose matching product IDs from `context.product_ids` too. Never use global ICP
UUID environment variables or accept catalog UUIDs invented by the model.

## Discovery memory

Use a **different Data Table for every workspace**, including lookup, insert,
update, novelty checks and any Level 2 queue. Preserve the existing registry
columns and add string columns `workspace_id` and `registry_key`.

```javascript
// Put workspace-runtime.js functions above this code.
const context = $('Workspace Guard').first().json.workspace_context;
const identity = registryRecordIdentity(context, $json);
// Write identity.workspace_id and identity.registry_key.
// For the existing DEV schema, write identity.domain to canonical_domain.
// Look up registry_key in context.registry_table_id.
```

For a returned row, call `assertRegistryRow(context, row)` before trusting its
status or candidate ID. Missing ownership is an error, not permission to reuse a
row. Keep Level 1/1.1's existing retry windows and one concurrent discovery run
per workspace; n8n Data Tables are not an atomic distributed claim mechanism.

For historic LorrySystem memory, export rows to a JSON array under `tmp/`, stop
that discovery schedule, and migrate a copy:

```bash
node integrations/n8n/bind-workflow.js migrate-memory \
  tmp/lorry-rows.json 00000000-0000-0000-0000-000000000001 tmp/lorry-scoped-rows.json
```

The migration preserves statuses, candidate IDs, evidence and retry fields,
normalizes company domains, and adds ownership keys. It supports the existing DEV
`canonical_domain` column without introducing an extra `domain` column. It includes
the canonical URL in keys for this discovery schema, preserving separate directory
pages on the same domain. It rejects duplicate discovery keys
and foreign-workspace rows. Unscoped historic rows can only be assigned to
LorrySystem. Create other products' tables empty. Review the result and import
it into the intended table using your installed n8n's table import facilities or
a temporary import workflow. Do not commit the exported business records.

## Sender accounts and separate schedules

Bind email/social nodes explicitly, for example:

```json
"sender_nodes": {
  "Send Email": {
    "credential_type": "gmailOAuth2",
    "credential": { "id": "N8N_GMAIL_ID", "name": "Product Alpha Email" }
  }
}
```

Check provider account identity in n8n before activation. Credential names cannot
prove which mailbox or page the provider authorized. Set each workspace's sender
address, reply-to, signature and social page/account IDs in its own workflow;
these fields are not automatically rewritten by the tool. Shared search/AI
credentials may be intentional, but shared sender or Marketing API credentials
across products are rejected by this cross-binding check:

```bash
node integrations/n8n/bind-workflow.js check-isolation \
  tmp/lorry-binding.json tmp/alpha-binding.json
```

An existing approval-aware execution workflow is still required before sending.
This package does not add sending, delivery claims, retries or a campaign engine.
Candidate acceptance and marketing approvals remain human API decisions. Named
automation credentials cannot perform those decisions. Set a schedule separately
for each workspace and review its API/provider usage; budget settings do not
enforce provider spend caps.

## Acceptance before activation

### Dashboard Find Leads

Discovered Leads now starts bounded discovery with a search phrase and 1–10 new
websites. Only workspace administrators/operators can start runs; a database
constraint allows one queued/running job per workspace. The page polls saved
status and refreshes the reviewable candidates when the run finishes. Counts
distinguish new candidates, existing candidates, skipped websites and failures.

The discovery child keeps its manual trigger and also accepts an Execute
Sub-workflow Trigger. Generate the dashboard dispatcher with
`dashboardDispatcher(binding, discoveryWorkflowId, webhookPath)` from
`dashboard-discovery.js`. Publish the child first, then the dispatcher; n8n 2.41
requires published referenced sub-workflows. The dispatcher webhook validates
the bound workspace and exchanges a one-use run proof at
`POST /api/discovery/runs/{id}/claim` using the named workspace API credential
before invoking search. It waits for the child and reports completion or a
sanitized failure at `/complete`. Unknown, expired, replayed and foreign-workspace
requests stop before Brave/model calls. Webhook execution data is not retained.
Do not add a search schedule: discovery runs only when a human starts a saved job.

The child returns one completion summary after all terminal branches, including
empty searches, all-skipped memory results, fetch failures and rejected
extractions. Dashboard runs only fetch unseen websites and never accept
candidates or send marketing. Fatal child errors are caught by the dispatcher;
a worker lost during a run times out rather than permanently blocking the button.

DEV startup registers the LorrySystem connection from `api/discovery.dev.json`
after migration 010, only when `APP_ENV=development` and no connection exists.
This is configuration, not a credential: the webhook cannot start discovery
without a genuine API-created run and its one-use proof. Existing administrator
settings (including disabled connections) are preserved. Production/test modes
do not inherit this DEV connection. Other products can connect their own
dispatcher in **Workspaces & team → Lead discovery**. Allowed destination hosts
are restricted by `DISCOVERY_WEBHOOK_ALLOWED_HOSTS` in the API environment;
DEV defaults to `n8n-dev.obsidian.cam`. An explicit `DISCOVERY_BOOTSTRAP_FILE`
can supply a different deployment's initial connection.

Validation includes the disposable `api/scripts/validate_discovery_runs.py`
integration suite and native n8n 2.41.7 runs covering a successful discovery,
all-skipped memory, empty search and fatal child failure. No paid providers are
called by these fixture tests.

Validate both workspaces independently: overlapping company domains do not
suppress each other; AI sees the correct catalog; candidates use that workspace's
ICP IDs; a swapped/revoked API credential stops the run; registry rows with wrong
ownership are rejected; provider account identity is correct; human approvals
remain required. Pause the old workflow before enabling its replacement.

Local regression and CI:

```bash
node --test integrations/n8n/workspace-runtime.test.js integrations/n8n/discovery.test.js integrations/n8n/research.test.js
```

The API's disposable integration suite separately verifies the context contract,
catalog isolation, credential revocation and research claims. Successful local
tests do not imply that live workflows have been imported or activated.

The preflight and candidate-submission path were also imported and executed in a
disposable n8n 2.41.7 instance against two test workspaces. Both created independent
candidates for the same prospect with their own ICP IDs and registry namespaces;
a swapped credential stopped before downstream execution. The full discovery graph
was also run in disposable n8n 2.41.7 with native Data Tables and synthetic provider
and candidate responses for two unrelated products. First runs passed candidate,
source and final registry checks; identical second runs skipped fetch, AI and
candidate creation. The custom-model version passed the same full graph using
an actual n8n HTTP Request against a local Chat Completions stub that checked
the model, JSON settings, workspace evidence and `x-api-key` header. A mismatched
workspace stopped before Brave Search. Sender
accounts and real extraction still need their own validation before activation.

References: [n8n HTTP credentials](https://docs.n8n.io/integrations/builtin/credentials/httprequest/),
[Data Table node](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.datatable/),
[referencing node output](https://docs.n8n.io/code/builtin/output-other-nodes/).

## Automatic research after acceptance

Accepting a discovered candidate already creates an official lead and one
`PENDING` research job in the same transaction. The workspace research worker
polls every minute; acceptance needs no second research button. Human review
remains required, and the worker does not qualify leads, create contacts or send
messages. Named people and their public business details are saved as research
findings for review.

Create two workflows using `research-binding.example.json`. Fill only credential
**references** from n8n: the workspace Marketing API credential, Brave Search and
the existing `xKiro DEV model API` Header Auth credential (`x-api-key`). xKiro's
key stays in n8n's credential store; no model key or runtime environment variable
is required. The model is `mistralai/mistral-large-2512` at
`https://api.xkiro.com/v1`.

```bash
node integrations/n8n/research-workflows.js child tmp/research-binding.json tmp/research-child.json
# Import and publish the child, then use its assigned n8n workflow ID:
node integrations/n8n/research-workflows.js worker tmp/research-binding.json tmp/research-worker.json CHILD_ID
```

Import and publish the queue workflow. Each product needs its own pair and named
workspace API credential. Both workflows verify current workspace identity and
active ICP/catalog IDs before work. The parent validates API readiness before
claiming a job: an older API without `/api/research/recover-stale` returns a
`WAITING_API_DEPLOYMENT` result. Once the new API is deployed, the next scheduled
tick starts processing automatically.

DEV is wired with the published
[Company Research child](https://n8n-dev.obsidian.cam/workflow/xlaOGqh9W1WE8kXj)
and [Automatic Research queue](https://n8n-dev.obsidian.cam/workflow/9uNygo8bhPT2RvEP).
The live readiness check confirmed it waits for the API deployment without
claiming the existing pending job or calling providers. Merge the API/dashboard
change into `develop` for the normal CI/CD deployment; the queue needs no further
activation afterwards. Older API versions can return either 404 or 405 for the
missing recovery route; both wait safely, while auth/server errors stop execution.

The parent claims at most one running job per workspace using an advisory lock
and `FOR UPDATE SKIP LOCKED`. Closed leads are excluded from automatic claims.
Jobs abandoned for 30 minutes become failed with retained history. An operator
can use **Run research again** on the lead page; duplicate pending/running jobs
are rejected. Source and completion writes remain scoped by PostgreSQL RLS.

Each job makes two Brave queries, fetches at most six pages through the API's
guarded public-fetch endpoint, saves at most ten sources, and sends at most
24,000 evidence characters to one xKiro call with 4,000 output tokens. Guarded
fetch retains robots checks, public-IP DNS pinning, bounded redirects and response
sizes. Search/website failures can still yield a useful partial report. Sources
are saved before extraction, so model failures retain readable evidence.

Extraction validates source membership, exact evidence quotes, public person
names/titles and contact attribution. Unsupported contacts are omitted; unknown
fleet and technology remain unknown. Completed research requires official-page
evidence, supported services and verified identity with confidence at least 70.
Otherwise useful findings are partial with confidence capped at 65. No supported
facts or a provider error fails the job with a sanitized reason. Raw provider
responses and credentials are not saved as dashboard data. n8n execution payload
retention is disabled in the deployed pair.

The lead's Research section displays company/services/fleet/technology findings,
public business contacts, per-finding confidence, quotes, source links and missing
information. It refreshes while work is pending/running and retains previous
runs when research is queued again.

Research is presented as a company brief, with a concise overview, grouped
findings, contact cards and an evidence sidebar. Citation numbers are consistent
across the report and point into its source library. The latest useful report
remains visible while a new job runs or after a retry fails; previous runs can
be opened from research history. Existing saved findings use the same layout
without needing to run the providers again. New extractions can also save a
short `title` for each finding; older untitled findings remain valid. The model
prompt requests focused plain-text findings, while the dashboard owns their
formatting and continues to escape untrusted source content.

Validation: `api/scripts/validate_workspace_research.py` covers acceptance,
concurrent claims, RLS, named-key guarded fetch, stale recovery, dashboard display,
retry CSRF and role restrictions in disposable environments. Native n8n 2.41.7
tests against the disposable API exercise two workspaces, empty queues, API
deployment waiting, partial evidence, model failure and a mismatched child using
synthetic website/search/model responses; these tests incur no provider charges.
