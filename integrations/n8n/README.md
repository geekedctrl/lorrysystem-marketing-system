# Workspace-aware n8n automation

This package adapts exported n8n workflows offline. It does not change a running
n8n instance or provision sender accounts. Workflow exports contain credential
references only; API keys and provider secrets stay in n8n credentials.

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
const identity = registryIdentity(context, $json.canonical_domain || $json.domain || $json.canonical_url);
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
`canonical_domain` column without introducing an extra `domain` column. It rejects duplicate domains
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

Validate both workspaces independently: overlapping company domains do not
suppress each other; AI sees the correct catalog; candidates use that workspace's
ICP IDs; a swapped/revoked API credential stops the run; registry rows with wrong
ownership are rejected; provider account identity is correct; human approvals
remain required. Pause the old workflow before enabling its replacement.

Local regression and CI:

```bash
node --test integrations/n8n/workspace-runtime.test.js
```

The API's disposable integration suite separately verifies the context contract,
catalog isolation, credential revocation and research claims. Successful local
tests do not imply that live workflows have been imported or activated.

The preflight and candidate-submission path were also imported and executed in a
disposable n8n 2.41.7 instance against two test workspaces. Both created independent
candidates for the same prospect with their own ICP IDs and registry namespaces;
a swapped credential stopped before downstream execution. Actual Data Table row
operations and sender accounts must still be verified in the target n8n instance.

References: [n8n HTTP credentials](https://docs.n8n.io/integrations/builtin/credentials/httprequest/),
[Data Table node](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.datatable/),
[referencing node output](https://docs.n8n.io/code/builtin/output-other-nodes/).
