'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { assertWorkspaceContext, registryIdentity, assertRegistryRow, icpId, assertCandidate,
  workspacePrompt } = require('./workspace-runtime');
const { bindWorkflow, validateIsolation, migrateMemory } = require('./bind-workflow');
const A = '10000000-0000-0000-0000-000000000001';
const B = '20000000-0000-0000-0000-000000000001';
function response(id = A, brand = 'Alpha') {
  return { workspace: { id, name: brand, role: 'SERVICE', settings: { brand_voice: brand } },
    automation: { contract_version: 1, credential_kind: 'workspace',
      registry_namespace: `workspace:${id}:discovery`, human_candidate_review_required: true,
      human_marketing_approval_required: true },
    icps: [{ id: `icp-${id}`, code: 'GENERAL', name: `${brand} customers`, qualification_rules: { sector: brand } }],
    products: [{ id: `product-${id}`, code: 'MAIN', name: `${brand} product` }] };
}
function binding(id = A) {
  return { workspace_id: id, api_base_url: 'http://marketing-api:8000',
    api_credential: { id: `api-${id}`, name: 'API' }, trigger_nodes: ['Start'],
    api_nodes: { 'Create Candidate': '/api/candidates' }, registry_table_id: `table-${id}`,
    registry_nodes: ['Memory'], sender_nodes: { Send: { credential_type: 'gmailOAuth2',
      credential: { id: `sender-${id}`, name: 'Sender' } } }, shared_nodes: ['AI'] };
}
function source() {
  return { name: 'Discovery', id: 'old-id', active: true, versionId: 'old-version',
    pinData: { Start: [{ json: { old_workspace_data: 'private' } }] }, staticData: { lastDomain: 'private' },
    nodes: [
      { name: 'Start', type: 'n8n-nodes-base.manualTrigger', typeVersion: 1, parameters: {} },
      { name: 'Memory', type: 'n8n-nodes-base.dataTable', typeVersion: 1,
        parameters: { operation: 'get', dataTableId: { value: 'old-table' } } },
      { name: 'Create Candidate', type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2,
        parameters: { method: 'POST', url: 'http://old-api/api/candidates',
          sendBody: true, specifyBody: 'json', jsonBody: '={{ $json.candidate }}',
          options: { response: { response: { fullResponse: true, neverError: true } } },
          headerParameters: { parameters: [{ name: 'X-API-Key', value: 'old-secret' },
            { name: 'Content-Type', value: 'application/json' }] } },
        credentials: { httpHeaderAuth: { id: 'old-api' } }, continueOnFail: true },
      { name: 'Send', type: 'n8n-nodes-base.gmail', typeVersion: 2,
        parameters: { operation: 'send' }, credentials: { gmailOAuth2: { id: 'old-sender' } } },
      { name: 'AI', type: '@n8n/n8n-nodes-langchain.openAi', typeVersion: 1,
        parameters: {}, credentials: { openAiApi: { id: 'shared-ai' } } },
    ], connections: { Start: { main: [[{ node: 'Memory', type: 'main', index: 0 }]] },
      Memory: { main: [[{ node: 'AI', type: 'main', index: 0 }]] } } };
}
const context = assertWorkspaceContext(response(), binding());

test('wrong credential, legacy key, user session and contract changes stop before work', () => {
  assert.throws(() => assertWorkspaceContext(response(B), binding()), /does not match/);
  for (const kind of ['legacy', 'user']) {
    const value = response(); value.automation.credential_kind = kind;
    assert.throws(() => assertWorkspaceContext(value, binding()), /named workspace/);
  }
  const user = response(); user.workspace.role = 'ADMIN';
  assert.throws(() => assertWorkspaceContext(user, binding()), /does not match/);
  const future = response(); future.automation.contract_version = 2;
  assert.throws(() => assertWorkspaceContext(future, binding()), /supported automation/);
  const memory = response(); memory.automation.registry_namespace = `workspace:${B}:discovery`;
  assert.throws(() => assertWorkspaceContext(memory, binding()), /supported automation/);
  const approval = response(); approval.automation.human_marketing_approval_required = false;
  assert.throws(() => assertWorkspaceContext(approval, binding()), /supported automation/);
});
test('empty or ambiguous catalogs stop discovery; non-discovery preflight can allow empty', () => {
  const empty = response(); empty.products = [];
  assert.throws(() => assertWorkspaceContext(empty, binding()), /Add active/);
  assert.doesNotThrow(() => assertWorkspaceContext(empty, { ...binding(), require_catalog: false }));
  const duplicate = response(); duplicate.icps.push(duplicate.icps[0]);
  assert.throws(() => assertWorkspaceContext(duplicate, binding()), /Invalid ICP/);
});
test('same company gets independent memory and catalog IDs in two products', () => {
  const beta = assertWorkspaceContext(response(B, 'Beta'), binding(B));
  const alphaRow = registryIdentity(context, 'https://WWW.Example.com/about');
  const betaRow = registryIdentity(beta, 'example.com');
  assert.equal(alphaRow.domain, 'example.com');
  assert.notEqual(alphaRow.registry_key, betaRow.registry_key);
  assert.notEqual(icpId(context, 'GENERAL'), icpId(beta, 'GENERAL'));
  assert.throws(() => assertRegistryRow(beta, alphaRow), /another workspace/);
  assert.throws(() => assertRegistryRow(context, { domain: 'example.com' }), /migrated/);
  assert.equal(assertRegistryRow(context, alphaRow), alphaRow);
  assert.equal(registryIdentity(context, 'https://example.com:443/path').domain, 'example.com');
  for (const url of ['ftp://example.com', 'https://user:password@example.com', 'https://bad..example.com']) {
    assert.throws(() => registryIdentity(context, url));
  }
});
test('unsupported AI ICP and foreign candidate UUID fail closed', () => {
  assert.throws(() => icpId(context, 'LOGISTICS_HAULAGE'), /unknown/);
  assert.throws(() => assertCandidate(context, { suggested_icp_profile_id: `icp-${B}` }), /does not belong/);
  assert.doesNotThrow(() => assertCandidate(context, { suggested_icp_profile_id: icpId(context, 'GENERAL') }));
});
test('all five prompts use current product context with no default LorrySystem catalog', () => {
  const beta = assertWorkspaceContext(response(B, 'Beta'), binding(B));
  for (const task of ['discovery', 'research', 'scoring', 'matching', 'drafting']) {
    const prompt = workspacePrompt(beta, task);
    assert.match(prompt, /Beta product/);
    assert.match(prompt, /Beta customers/);
    assert.doesNotMatch(prompt, /Alpha product|AI_DASHCAM|LOGISTICS_HAULAGE/);
  }
});
test('binding rewires preflight, API, memory and sender without mutating source', () => {
  const original = source();
  const workflow = bindWorkflow(original, binding());
  assert.equal(original.active, true);
  assert.equal(original.nodes[1].parameters.dataTableId.value, 'old-table');
  assert.equal(workflow.active, false);
  assert.equal(workflow.pinData, undefined);
  assert.equal(workflow.staticData, undefined);
  assert.equal(workflow.id, undefined);
  assert.equal(workflow.connections.Start.main[0][0].node, 'Workspace Configuration');
  assert.equal(workflow.connections['Workspace Guard'].main[0][0].node, 'Memory');
  const api = workflow.nodes.find(node => node.name === 'Create Candidate');
  assert.equal(api.credentials.httpHeaderAuth.id, `api-${A}`);
  assert.equal(api.continueOnFail, undefined);
  assert.equal(api.parameters.jsonBody, '={{ $json.candidate }}');
  assert.equal(api.parameters.options.response.response.fullResponse, true);
  assert.equal(api.parameters.options.response.response.neverError, false);
  assert.equal(api.parameters.headerParameters.parameters.at(-1).value, A);
  assert.doesNotMatch(JSON.stringify(workflow), /old-secret|old-api|old-sender|old-table/);
  assert.equal(workflow.nodes.find(node => node.name === 'Memory').parameters.dataTableId.value, `table-${A}`);
  assert.equal(workflow.nodes.find(node => node.name === 'Send').credentials.gmailOAuth2.id, `sender-${A}`);
});
test('generated n8n Code nodes execute with actual n8n-style inputs and stop on mismatch', () => {
  const workflow = bindWorkflow(source(), binding());
  const configurationNode = workflow.nodes.find(node => node.name === 'Workspace Configuration');
  const guardNode = workflow.nodes.find(node => node.name === 'Workspace Guard');
  const run = (code, input, configuration) => vm.runInNewContext(`(function(){${code}\n})()`, {
    $input: { all: () => input, first: () => input[0] },
    $: () => ({ first: () => configuration[0], all: () => configuration }),
  });
  const configuration = run(configurationNode.parameters.jsCode,
    [{ json: { query: 'Alpha' }, binary: { document: { id: 'binary-a' } } }, { json: { query: 'Second' } }]);
  const output = run(guardNode.parameters.jsCode, [{ json: response() }, { json: response() }], configuration);
  assert.equal(output[0].json.query, 'Alpha');
  assert.equal(output[0].json.workspace_context.workspace_id, A);
  assert.equal(output[0].binary.document.id, 'binary-a');
  assert.equal(output[1].json.query, 'Second');
  assert.equal(output[1].pairedItem.item, 1);
  assert.throws(() => run(guardNode.parameters.jsCode, [{ json: response(B) }, { json: response() }], configuration), /does not match/);
});
test('unmapped credentials, senders, memory and entry points are rejected', () => {
  for (const key of ['api_nodes', 'registry_nodes', 'sender_nodes', 'shared_nodes']) {
    const value = binding(); delete value[key];
    assert.throws(() => bindWorkflow(source(), value), /Unclassified/);
  }
  const extra = source(); extra.nodes.push({ name: 'Scheduled', type: 'n8n-nodes-base.scheduleTrigger' });
  assert.throws(() => bindWorkflow(extra, binding()), /Every workflow trigger/);
  const sub = source(); sub.nodes.push({ name: 'Child', type: 'n8n-nodes-base.executeWorkflow' });
  assert.throws(() => bindWorkflow(sub, binding()), /Sub-workflows/);
  const anonymousApi = source(); anonymousApi.nodes.push({ name: 'Old API',
    type: 'n8n-nodes-base.httpRequest', parameters: { url: 'http://old-api/api/leads' } });
  assert.throws(() => bindWorkflow(anonymousApi, binding()), /Unclassified/);
});
test('shared sender and registry references across products are rejected', () => {
  validateIsolation([binding(), binding(B)]);
  const table = binding(B); table.registry_table_id = binding().registry_table_id;
  assert.throws(() => validateIsolation([binding(), table]), /registry table/);
  const sender = binding(B); sender.sender_nodes.Send = binding().sender_nodes.Send;
  assert.throws(() => validateIsolation([binding(), sender]), /sender credential/);
  const api = binding(B); api.api_credential = binding().api_credential;
  assert.throws(() => validateIsolation([binding(), api]), /API or sender/);
});
test('legacy registry migration preserves statuses, source evidence and candidate IDs', () => {
  const id = '00000000-0000-0000-0000-000000000001';
  const rows = [{ domain: 'www.example.com', status: 'ACCEPTED', candidate_id: 'candidate-a', source: 'Evidence' }];
  const migrated = migrateMemory(rows, id);
  assert.equal(migrated[0].status, 'ACCEPTED');
  assert.equal(migrated[0].candidate_id, 'candidate-a');
  assert.equal(migrated[0].domain, 'example.com');
  assert.equal(migrated[0].workspace_id, id);
  assert.equal(rows[0].workspace_id, undefined);
  assert.throws(() => migrateMemory(rows, B), /only be assigned to LorrySystem/);
  assert.throws(() => migrateMemory(migrated, B), /foreign rows/);
  assert.throws(() => migrateMemory([...rows, ...rows], id), /Duplicate/);
});
test('checked-in preflight matches generator and is inactive', () => {
  const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, 'workspace-preflight.json'), 'utf8'));
  assert.equal(fixture.active, false);
  assert.equal(fixture.nodes.find(node => node.name === 'Workspace Guard').parameters.jsCode,
    bindWorkflow({ name: 'Workspace preflight', nodes: [{ name: 'Manual Trigger',
      type: 'n8n-nodes-base.manualTrigger', typeVersion: 1, parameters: {} }],
      connections: { 'Manual Trigger': { main: [[]] } } }, {
        ...binding('00000000-0000-0000-0000-000000000001'), trigger_nodes: ['Manual Trigger'],
        api_nodes: {}, registry_nodes: [], sender_nodes: {}, shared_nodes: [],
      }).nodes.find(node => node.name === 'Workspace Guard').parameters.jsCode);
});
