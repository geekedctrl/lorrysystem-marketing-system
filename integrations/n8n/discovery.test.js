'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const {adaptDiscovery, discoverySettings} = require('./adapt-discovery');
const {registryRecordIdentity} = require('./workspace-runtime');
const {migrateMemory} = require('./bind-workflow');
const example = JSON.parse(fs.readFileSync(path.join(__dirname,'discovery-binding.example.json'),'utf8'));
const A = example.workspace_id;
const B = '00000000-0000-0000-0000-000000000002';
const ctx = (id, code = 'ACCOUNTING_FIRMS') => ({workspace_id:id, registry_namespace:`workspace:${id}:discovery`,
  icp_ids:{[code]:id === A ? '10000000-0000-0000-0000-000000000001':'20000000-0000-0000-0000-000000000001'}});
const workflow = adaptDiscovery(example);
function run(name, json, context, previous = {}) {
  const node = workflow.nodes.find(node => node.name === name);
  const $ = name => {
    const value = name === 'Workspace Guard' ? {workspace_context:context}
      : name === 'Workspace Configuration' ? {config: {discovery: discoverySettings(example.discovery)}} : previous[name];
    if (!value) throw new Error(`Missing fixture node: ${name}`);
    return {item: {json:value}, first: () => ({json:value}), all: () => [{json:value}]};
  };
  // n8n's sandbox has neither URL nor module globals.
  return vm.runInNewContext(`(function(){${node.parameters.jsCode}\n})()`,
    {$json:json, $input:{all:() => [{json}]}, $}, {timeout:1000});
}

test('the supplied discovery graph binds all 12 memory nodes and stops API auth errors', () => {
  assert.equal(workflow.nodes.length,62);
  assert.equal(workflow.active,false);
  assert.equal(workflow.nodes.some(node => /gmail|emailSend|executeCommand/.test(node.type)),false);
  const tables=workflow.nodes.filter(node => node.type === 'n8n-nodes-base.dataTable');
  assert.equal(tables.length,12);
  for (const node of tables) {
    assert.equal(node.parameters.dataTableId.value, example.registry_table_id);
    if (node.parameters.filters) {
      assert.equal(node.parameters.matchType,'allConditions');
      assert.deepEqual(node.parameters.filters.conditions.map(c => c.keyName),['canonical_url','workspace_id','registry_key']);
    }
    if (node.parameters.columns) {
      assert.ok(node.parameters.columns.value.workspace_id);
      assert.ok(node.parameters.columns.value.registry_key);
    }
  }
  for (const name of ['Load Workspace Context','Create Candidate','Verify Candidate Detail','Verify Workspace Access']) {
    const node = workflow.nodes.find(node => node.name === name);
    assert.equal(node.credentials.httpHeaderAuth.id,example.api_credential.id);
    assert.equal(node.parameters.headerParameters.parameters.at(-1).value,A);
    assert.equal(node.onError,undefined);
    assert.equal(node.parameters.options.redirect.redirect.followRedirects,false);
    assert.notEqual(node.parameters.options.response?.response?.neverError,true);
  }
  for (const node of workflow.nodes.filter(node => node.type === 'n8n-nodes-base.code')) {
    assert.doesNotThrow(() => new vm.Script(`(function(){${node.parameters.jsCode}\n})()`), node.name);
  }
  const text = JSON.stringify(workflow);
  assert.equal(text.includes('LOGISTICS_HAULAGE'),false);
  assert.equal(text.includes('http://marketing-api'),false);
  assert.equal(text.includes('lorrysystem-dashboard'),false);
});

test('two unrelated products classify the same company using current catalog IDs', () => {
  const source = {url:'https://example.com/', domain:'example.com', canonical_domain:'example.com', canonical_url:'https://example.com/',
    query:'accounting firms Malaysia',title:'Example Accounting',clean_text:'Accounting firm. '.repeat(25)};
  const ai = {company_name:'Example Accounting',suggested_icp:'ACCOUNTING_FIRMS',icp_confidence:0.9,
    icp_reasoning:'Explicit accounting practice',source_summary:'An accounting firm',services:['Accounting']};
  for (const id of [A,B]) {
    const context=ctx(id);
    const normalized=run('Normalize Discovery Key',source,context).json;
    assert.equal(normalized.workspace_id,id);
    assert.equal(normalized.registry_key, `workspace:${id}:discovery:https://example.com/`);
    assert.equal(run('Cheap Relevance Gate',source,context).json.relevance_pass,true);
    const extracted=run('Validate AI Extraction',ai,context,{'Cheap Relevance Gate':normalized}).json;
    assert.equal(extracted.candidate_eligible,true);
    const payload=run('Build Candidate Payload',extracted,context).json.candidate_payload;
    assert.equal(payload.suggested_icp_profile_id,context.icp_ids.ACCOUNTING_FIRMS);
  }
  const bad=run('Validate AI Extraction',{...ai,suggested_icp:'LOGISTICS_HAULAGE'},ctx(B),{'Cheap Relevance Gate':source}).json;
  assert.equal(bad.ai_extraction_error,'INVALID_ICP_CODE');
  assert.equal(bad.candidate_eligible,false);
  const noFit=run('Validate AI Extraction',{...ai,suggested_icp:null},ctx(B),{'Cheap Relevance Gate':source}).json;
  assert.equal(noFit.ai_extraction_status,'VALID');
  assert.equal(noFit.candidate_eligible,false);
});

test('directory page keys survive migration without suppressing different listings', () => {
  const rows = ['/company/a','/company/b'].map(path => ({canonical_domain:'businesslist.my',canonical_url:`https://businesslist.my${path}`,
    status:'CANDIDATE_CREATED',candidate_id:path, times_seen:5}));
  const migrated=migrateMemory(rows,A);
  assert.notEqual(migrated[0].registry_key,migrated[1].registry_key);
  assert.equal(migrated[0].candidate_id,rows[0].candidate_id);
  assert.equal(migrated[0].times_seen,5);
  const normalized=run('Normalize Discovery Key',{url:rows[0].canonical_url,is_directory_source:true},ctx(A)).json;
  assert.equal(normalized.registry_key,migrated[0].registry_key);
  assert.throws(() => registryRecordIdentity(ctx(A),{canonical_domain:'example.com',canonical_url:'https://other.com/'}),/match/);
});

test('memory skip and retry behavior requires a row owned by the current workspace', () => {
  const source={url:'https://example.com/',canonical_domain:'example.com',canonical_url:'https://example.com/'};
  const identity=registryRecordIdentity(ctx(A),source);
  const row={...source,...identity,id:1,status:'CANDIDATE_CREATED',times_seen:2};
  const previous={'Normalize Discovery Key':source};
  const skip=run('Prepare Existing Registry Decision',row,ctx(A),previous).json;
  assert.equal(skip.registry_should_process,false);
  assert.equal(skip.registry_times_seen,3);
  assert.throws(() => run('Prepare Existing Registry Decision',row,ctx(B),previous),/another workspace/);
  const delayed=run('Prepare Existing Registry Decision',{...row,status:'FETCH_FAILED',retry_after:'2099-01-01T00:00:00Z'},ctx(A),previous).json;
  assert.equal(delayed.registry_should_process,false);
  const due=run('Prepare Existing Registry Decision',{...row,status:'FETCH_FAILED',retry_after:'2020-01-01T00:00:00Z'},ctx(A),previous).json;
  assert.equal(due.registry_should_process,true);
});

test('public URL normalization keeps pairing and excludes internal targets', () => {
  const results=['http://127.0.0.1/','http://localhost/','http://user:password@example.com/','http://service.internal/',
    'http://example.com:8000/','https://businesslist.my/company/a','https://businesslist.my/company/b',
    'https://example.com/?utm_source=test','https://example.com/about','https://other.com/?bad%=value'].map(url => ({url,title:'A company'}));
  const node=workflow.nodes.find(node => node.name === 'Normalize & Filter URLs');
  const discovery=discoverySettings(example.discovery);
  const $ = name => ({first:()=>({json:name === 'Discovery Inputs' ? discovery : {config:{discovery}}}),
    all:()=>[{json:discovery}]});
  const output=vm.runInNewContext(`(function(){${node.parameters.jsCode}\n})()`,{$,$input:{all:()=>[{json:{web:{results}}}]}}, {timeout:1000});
  assert.equal(output.length,4);
  assert.equal(output.filter(item => item.json.is_directory_source).length,2);
  assert.equal(output.every(item => item.pairedItem.item === 0),true);
  const source={url:'https://example.com/'};
  assert.equal(run('Classify Fetch Result',{statusCode:302,body:'x'.repeat(500)},ctx(A),{'Normalize Discovery Key':source}).json.failure_reason,'REDIRECT_REQUIRES_VALIDATION');
});

test('discovery settings bound scanning and never accept secrets in credential references', () => {
  assert.throws(() => adaptDiscovery({...example,discovery:{...example.discovery,query:''}}),/query/);
  assert.throws(() => adaptDiscovery({...example,discovery:{...example.discovery,max_results_scanned:10000}}),/integer/);
  assert.throws(() => adaptDiscovery({...example,require_catalog:false}),/requires/);
  assert.throws(() => adaptDiscovery({...example,brave_credential:{...example.brave_credential,value:'secret'}}),/never a key/);
});

test('result scanning obeys its limit even when Brave returns a full page', () => {
  const node=workflow.nodes.find(node => node.name === 'Normalize & Filter URLs');
  const discovery=discoverySettings({...example.discovery,max_results_scanned:1});
  const $ = name => ({first:()=>({json:name === 'Discovery Inputs' ? discovery : {config:{discovery}}}),
    all:()=>[{json:discovery}]});
  const output=vm.runInNewContext(`(function(){${node.parameters.jsCode}\n})()`, {$,
    $input:{all:()=>[{json:{web:{results:[{url:'https://first.com/'},{url:'https://second.com/'}]}}}]}}, {timeout:1000});
  assert.equal(output.length,1);
  assert.equal(output[0].json.raw_results_scanned,1);
});
