#!/usr/bin/env node
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { bindWorkflow } = require('./bind-workflow');

function providerCredential(value, label) {
  if (!value || typeof value.id !== 'string' || !value.id.trim()
      || typeof value.name !== 'string' || !value.name.trim()
      || Object.keys(value).some(key => !['id', 'name'].includes(key))) {
    throw new Error(`${label} must contain only n8n credential id and name, never a key`);
  }
  return {id: value.id, name: value.name};
}

function discoverySettings(settings) {
  if (!settings || typeof settings.query !== 'string' || !settings.query.trim()
      || settings.query.length > 1000 || !/^[A-Z]{2}$/.test(settings.country || '')) {
    throw new Error('Set a workspace discovery query and two-letter country');
  }
  const integer = (name, fallback, maximum) => {
    const value = settings[name] ?? fallback;
    if (!Number.isInteger(value) || value < 1 || value > maximum) {
      throw new Error(`${name} must be an integer from 1 to ${maximum}`);
    }
    return value;
  };
  const strings = (name, maximum) => {
    const values = settings[name] ?? [];
    if (!Array.isArray(values) || values.length > maximum
        || values.some(value => typeof value !== 'string' || !value.trim() || value.length > 200)) {
      throw new Error(`${name} must be a short array of literal strings`);
    }
    return [...new Set(values.map(value => value.trim().toLowerCase()))];
  };
  const directories = strings('directory_domains', 100);
  if (directories.some(domain => !/^[a-z0-9.-]+\.[a-z]{2,}$/.test(domain))) {
    throw new Error('directory_domains must be domain names, not URLs');
  }
  return {query: settings.query.trim(), country: settings.country,
    brave_count: integer('brave_count', 20, 20),
    target_new_companies: integer('target_new_companies', 10, 40),
    max_results_scanned: integer('max_results_scanned', 40, 200),
    relevance_keywords: strings('relevance_keywords', 100), directory_domains: directories};
}

function adaptDiscovery(binding) {
  if (binding.require_catalog === false) throw new Error('Discovery requires active workspace catalogs');
  const source = JSON.parse(fs.readFileSync(path.join(__dirname, 'workspace-discovery.template.json'), 'utf8'));
  const brave = providerCredential(binding.brave_credential, 'brave_credential');
  const openai = providerCredential(binding.openai_credential, 'openai_credential');
  source.nodes.find(node => node.name === 'Brave Search').credentials = {httpHeaderAuth: brave};
  source.nodes.find(node => node.name === 'OpenAI Structured Extraction').credentials = {openAiApi: openai};
  const result = bindWorkflow(source, {
    ...binding, require_catalog: true, discovery: discoverySettings(binding.discovery),
    trigger_nodes: ['Manual Trigger'],
    api_nodes: {'Create Candidate': '/api/candidates',
      'Verify Candidate Detail': '/api/candidates/{{ $json.candidate_id }}',
      'Verify Workspace Access': '/api/workspace-context'},
    registry_nodes: source.nodes.filter(node => node.type === 'n8n-nodes-base.dataTable').map(node => node.name),
    sender_nodes: {}, shared_nodes: ['Brave Search', 'OpenAI Structured Extraction'],
  });
  result.name = `Workspace Lead Discovery — ${binding.workspace_id}`;
  return result;
}

module.exports = {adaptDiscovery, discoverySettings};
if (require.main === module) {
  try {
    if (process.argv.length !== 4) throw new Error('Usage: node adapt-discovery.js BINDING.json OUTPUT.json');
    const binding = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
    fs.writeFileSync(process.argv[3], JSON.stringify(adaptDiscovery(binding), null, 2)+'\n', {flag: 'wx'});
    console.log('Discovery copy generated inactive. Select real workspace/provider credentials before running.');
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
