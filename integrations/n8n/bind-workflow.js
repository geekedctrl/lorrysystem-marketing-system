#!/usr/bin/env node
/* Bind an exported workflow offline. Never reads or writes credential secrets. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { registryRecordIdentity } = require('./workspace-runtime');
const runtime = fs.readFileSync(path.join(__dirname, 'workspace-runtime.js'), 'utf8').replace(/\r\n/g, '\n');
const CONFIG = 'Workspace Configuration';
const FETCH = 'Load Workspace Context';
const GUARD = 'Workspace Guard';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SENDER = /(?:gmail|emailSend|microsoftOutlook|linkedIn|facebookGraphApi|twitter|instagram)/i;

function credential(value, label) {
  if (!value || typeof value.id !== 'string' || !value.id.trim()
      || typeof value.name !== 'string' || !value.name.trim()
      || Object.keys(value).some(key => !['id', 'name'].includes(key))) {
    throw new Error(`${label} must contain only the n8n credential id and name`);
  }
  return { id: value.id, name: value.name };
}

function validateBinding(binding) {
  if (!UUID.test(binding.workspace_id || '')) throw new Error('Set workspace_id to a UUID');
  const url = new URL(binding.api_base_url);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password
      || url.search || url.hash || !['', '/'].includes(url.pathname)) {
    throw new Error('api_base_url must be a fixed HTTP(S) origin without secrets');
  }
  credential(binding.api_credential, 'api_credential');
  if (!Array.isArray(binding.trigger_nodes) || !binding.trigger_nodes.length) {
    throw new Error('Explicitly list every trigger node');
  }
  if (new Set(binding.trigger_nodes).size !== binding.trigger_nodes.length) {
    throw new Error('Duplicate trigger binding');
  }
  if ((binding.registry_nodes || []).length && !binding.registry_table_id) {
    throw new Error('Set the dedicated workspace registry_table_id');
  }
  if (binding.registry_table_id && (typeof binding.registry_table_id !== 'string'
      || binding.registry_table_id.includes('{{'))) throw new Error('Use a fixed registry table id');
  for (const [name, sender] of Object.entries(binding.sender_nodes || {})) {
    if (!sender.credential_type || typeof sender.credential_type !== 'string') {
      throw new Error(`Set the sender credential type for ${name}`);
    }
    credential(sender.credential, `sender ${name}`);
  }
}

function preflightNodes(binding) {
  validateBinding(binding);
  const config = {
    workspace_id: binding.workspace_id,
    api_base_url: binding.api_base_url.replace(/\/$/, ''),
    registry_table_id: binding.registry_table_id || null,
    require_catalog: binding.require_catalog !== false,
    ...(binding.discovery ? { discovery: binding.discovery } : {}),
    ...(binding.llm ? { llm: binding.llm } : {}),
  };
  return [
    { id: 'workspace-configuration', name: CONFIG, type: 'n8n-nodes-base.code', typeVersion: 2,
      position: [260, 0], parameters: { mode: 'runOnceForAllItems', jsCode:
        `const config = ${JSON.stringify(config)};\n` +
        'return $input.all().map((item, index) => ({json: {config, run_input: item.json},\n' +
        '  ...(item.binary ? {binary: item.binary} : {}), pairedItem: {item: index}}));' } },
    { id: 'workspace-context-fetch', name: FETCH, type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2,
      position: [520, 0], parameters: {
        method: 'GET', url: `={{ $('${CONFIG}').first().json.config.api_base_url }}/api/workspace-context`,
        authentication: 'genericCredentialType', genericAuthType: 'httpHeaderAuth',
        sendHeaders: true, headerParameters: { parameters: [
          { name: 'X-Workspace-ID', value: binding.workspace_id },
        ] }, options: { timeout: 15000, redirect: { redirect: { followRedirects: false } } },
      }, credentials: { httpHeaderAuth: credential(binding.api_credential, 'api_credential') } },
    { id: 'workspace-guard', name: GUARD, type: 'n8n-nodes-base.code', typeVersion: 2,
      position: [780, 0], parameters: { mode: 'runOnceForAllItems', jsCode:
        `${runtime}\nconst configurations = $('${CONFIG}').all();\n` +
        'const inputs = $input.all();\n' +
        "if (inputs.length !== configurations.length) throw new Error('Workspace preflight input count changed');\n" +
        'return inputs.map((item, index) => {\n' +
        '  const original = configurations[index];\n' +
        '  const context = assertWorkspaceContext(item.json, original.json.config);\n' +
        "  return {json: {...original.json.run_input, workspace_context: context, workspace_prompt: workspacePrompt(context, 'discovery')},\n" +
        '    ...(original.binary ? {binary: original.binary} : {}), pairedItem: {item: index}};\n});' } },
  ];
}

function connection(node) { return { node, type: 'main', index: 0 }; }

function bindWorkflow(source, binding) {
  validateBinding(binding);
  if (!source || !Array.isArray(source.nodes) || !source.connections) {
    throw new Error('Input must be one exported n8n workflow object');
  }
  const result = structuredClone(source);
  const nodes = new Map(result.nodes.map(node => [node.name, node]));
  if (nodes.size !== result.nodes.length) throw new Error('Duplicate node names');
  for (const name of [CONFIG, FETCH, GUARD]) {
    if (nodes.has(name)) throw new Error('Input is already bound; use the original export');
  }
  if (result.nodes.some(node => node.type?.includes('executeWorkflow'))) {
    throw new Error('Sub-workflows need their own binding; review them before adapting this workflow');
  }
  const triggers = result.nodes.filter(node => /Trigger$|\.webhook$/.test(node.type || ''));
  if (triggers.some(node => !binding.trigger_nodes.includes(node.name))
      || binding.trigger_nodes.some(name => !triggers.some(node => node.name === name))) {
    throw new Error('Every workflow trigger must be explicitly bound');
  }
  // Requiring one trigger avoids schedule/webhook merges with incompatible inputs.
  if (triggers.length !== 1) throw new Error('Use one trigger per workspace workflow; split additional entry points');
  const trigger = triggers[0];
  if (trigger.disabled || trigger.continueOnFail || trigger.onError === 'continueRegularOutput') {
    throw new Error('The workflow trigger must be enabled and stop on error');
  }
  const old = result.connections[trigger.name];
  if (!old || Object.keys(old).some(key => key !== 'main') || old.main.length !== 1) {
    throw new Error('Trigger must have exactly one main output');
  }
  const classified = new Set(binding.trigger_nodes);
  const getNode = name => {
    if (classified.has(name)) throw new Error(`Node classified twice: ${name}`);
    const node = nodes.get(name);
    if (!node) throw new Error(`Unknown binding node: ${name}`);
    classified.add(name);
    return node;
  };
  for (const [name, endpoint] of Object.entries(binding.api_nodes || {})) {
    const node = getNode(name);
    if (node.type !== 'n8n-nodes-base.httpRequest' || node.typeVersion < 4) {
      throw new Error(`API node ${name} must use HTTP Request version 4`);
    }
    if (typeof endpoint !== 'string' || !endpoint.startsWith('/api/')
        || /[\r\n]|:\/\/|^\/api\/(?:auth|workspaces)(?:\/|$)/.test(endpoint)
        || endpoint.split(/[/?#]/).includes('..')) {
      throw new Error(`Use a business API path for ${name}`);
    }
    const p = node.parameters;
    p.url = `={{ $('${CONFIG}').first().json.config.api_base_url }}${endpoint}`;
    p.authentication = 'genericCredentialType';
    p.genericAuthType = 'httpHeaderAuth';
    // Reject hidden auth in alternate JSON header modes; never copy it into output.
    if (p.specifyHeaders === 'json' || p.jsonHeaders) {
      throw new Error(`Convert ${name} to header parameters and remove inline secrets first`);
    }
    p.sendHeaders = true;
    p.headerParameters = { parameters: [
      ...(p.headerParameters?.parameters || []).filter(header =>
        !['x-api-key', 'authorization', 'x-workspace-id'].includes(String(header.name).toLowerCase())),
      { name: 'X-Workspace-ID', value: binding.workspace_id },
    ] };
    p.options = { ...p.options, redirect: { redirect: { followRedirects: false } } };
    // Never continue a rejected API request into extraction, sending or state updates.
    if (p.options.response?.response) {
      p.options.response.response = { ...p.options.response.response, neverError: false };
    }
    node.credentials = { httpHeaderAuth: credential(binding.api_credential, 'api_credential') };
    delete node.continueOnFail;
    delete node.onError;
  }
  for (const name of binding.registry_nodes || []) {
    const node = getNode(name);
    if (node.type !== 'n8n-nodes-base.dataTable' || node.parameters.resource === 'table') {
      throw new Error(`Registry node ${name} must operate on Data Table rows`);
    }
    node.parameters.dataTableId = { __rl: true, mode: 'id', value: binding.registry_table_id };
  }
  for (const [name, sender] of Object.entries(binding.sender_nodes || {})) {
    const node = getNode(name);
    if (node.type === 'n8n-nodes-base.code') throw new Error('Use credential-aware sender nodes, not Code');
    node.credentials = { [sender.credential_type]: credential(sender.credential, `sender ${name}`) };
  }
  for (const name of binding.shared_nodes || []) {
    const node = getNode(name);
    if (SENDER.test(node.type || '')) throw new Error(`Sender ${name} needs an explicit workspace binding`);
  }
  for (const node of result.nodes) {
    const apiLikeRequest = node.type === 'n8n-nodes-base.httpRequest'
      && (String(node.parameters.url || '').includes('/api/')
        || (node.parameters.headerParameters?.parameters || []).some(header =>
          String(header.name).toLowerCase() === 'x-api-key'));
    if ((node.credentials && Object.keys(node.credentials).length || SENDER.test(node.type || '')
        || node.type === 'n8n-nodes-base.dataTable' || apiLikeRequest) && !classified.has(node.name)) {
      throw new Error(`Unclassified credential, sender or Data Table node: ${node.name}`);
    }
    if (node.type === 'n8n-nodes-base.executeCommand') {
      throw new Error('Execute Command nodes require manual review before workspace adaptation');
    }
  }
  result.nodes.push(...preflightNodes(binding));
  result.connections[trigger.name] = { main: [[connection(CONFIG)]] };
  result.connections[CONFIG] = { main: [[connection(FETCH)]] };
  result.connections[FETCH] = { main: [[connection(GUARD)]] };
  result.connections[GUARD] = old;
  result.name = `${source.name || 'Automation'} — ${binding.workspace_id}`;
  result.active = false;
  result.settings = { ...result.settings, saveManualExecutions: false,
    saveDataSuccessExecution: 'none', saveDataErrorExecution: 'none' };
  for (const key of ['id', 'versionId', 'activeVersionId', 'createdAt', 'updatedAt', 'meta',
    'pinData', 'staticData', 'shared', 'tags', 'triggerCount']) delete result[key];
  return result;
}

function validateIsolation(bindings) {
  const tables = new Map();
  const credentials = new Map();
  for (const binding of bindings) {
    validateBinding(binding);
    if (binding.registry_table_id) {
      const previous = tables.get(binding.registry_table_id);
      if (previous && previous !== binding.workspace_id) throw new Error('Workspaces share a discovery registry table');
      tables.set(binding.registry_table_id, binding.workspace_id);
    }
    for (const reference of [binding.api_credential,
      ...Object.values(binding.sender_nodes || {}).map(sender => sender.credential)]) {
      const previous = credentials.get(reference.id);
      if (previous && previous !== binding.workspace_id) throw new Error('Workspaces share an API or sender credential');
      credentials.set(reference.id, binding.workspace_id);
    }
  }
}

function migrateMemory(rows, workspaceId) {
  if (!UUID.test(workspaceId || '')) throw new Error('Set workspace_id to a UUID');
  const context = { workspace_id: workspaceId, registry_namespace: `workspace:${workspaceId}:discovery` };
  const seen = new Set();
  return rows.map(row => {
    if ((!row.workspace_id && workspaceId !== '00000000-0000-0000-0000-000000000001')
        || (row.workspace_id && row.workspace_id !== workspaceId)) {
      throw new Error('Unscoped historic rows may only be assigned to LorrySystem; foreign rows cannot be copied');
    }
    const identity = registryRecordIdentity(context, row);
    if (row.registry_key && row.registry_key !== identity.registry_key) throw new Error('Foreign registry key');
    if (seen.has(identity.registry_key)) throw new Error('Duplicate canonical domains; resolve before importing');
    seen.add(identity.registry_key);
    return { ...row, workspace_id: identity.workspace_id, registry_key: identity.registry_key,
      [Object.hasOwn(row, 'canonical_domain') ? 'canonical_domain' : 'domain']: identity.domain };
  });
}

function cli(args) {
  const read = filename => JSON.parse(fs.readFileSync(filename, 'utf8'));
  const write = (filename, value) => fs.writeFileSync(filename, JSON.stringify(value, null, 2) + '\n', { flag: 'wx' });
  if (args[0] === 'bind' && args.length === 4) {
    write(args[3], bindWorkflow(read(args[1]), read(args[2])));
  } else if (args[0] === 'check-isolation' && args.length >= 3) {
    validateIsolation(args.slice(1).map(read));
  } else if (args[0] === 'migrate-memory' && args.length === 4) {
    write(args[3], migrateMemory(read(args[1]), args[2]));
  } else {
    throw new Error('Usage: bind WORKFLOW.json BINDING.json OUTPUT.json | check-isolation BINDING_A.json BINDING_B.json | migrate-memory ROWS.json WORKSPACE_UUID OUTPUT.json');
  }
  console.log('Workspace adaptation check completed. Output remains inactive; review prompts and memory mappings before activation.');
}

module.exports = { bindWorkflow, preflightNodes, validateBinding, validateIsolation, migrateMemory };
if (require.main === module) {
  try { cli(process.argv.slice(2)); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
