'use strict';
const fs = require('node:fs');
const path = require('node:path');

function edge(node, index=0) { return {node, type:'main', index}; }
function code(name, jsCode, position) {
  return {id:name.toLowerCase().replace(/\W+/g,'-'),name,type:'n8n-nodes-base.code',typeVersion:2,position,parameters:{jsCode}};
}

function addDashboardInput(workflow) {
  const input = {id:'dashboard-run-input',name:'Dashboard Run Input',type:'n8n-nodes-base.executeWorkflowTrigger',
    typeVersion:1.1,position:[-1000,300],parameters:{inputSource:'passthrough'}};
  workflow.nodes.push(input);
  workflow.connections[input.name] = {main:[[edge('Workspace Configuration')]]};
  const discovery = workflow.nodes.find(node => node.name === 'Discovery Inputs');
  discovery.parameters.jsCode = `let dashboard = null;
try { dashboard = $('Dashboard Run Input').first().json; } catch (_) {}
const configured = $('Workspace Configuration').first().json.config.discovery;
const context = $('Workspace Guard').first().json.workspace_context;
if (dashboard && (dashboard.workspace_id !== context.workspace_id || dashboard.status !== 'RUNNING'
    || typeof dashboard.query !== 'string' || dashboard.query.length > 300
    || !Number.isInteger(dashboard.target_new_companies) || dashboard.target_new_companies < 1 || dashboard.target_new_companies > 10)) {
  throw new Error('Dashboard discovery request does not match this workspace');
}
const discovery = dashboard ? {...configured, query:dashboard.query, target_new_companies:dashboard.target_new_companies,
  max_results_scanned:40, brave_count:20, new_only:true} : configured;
if (!discovery.query) throw new Error('Configure this workspace discovery query');
return [{json:{...discovery, brave_offset:0, new_companies_found:0, results_scanned:0},pairedItem:{item:0}}];`;
  const decision = workflow.nodes.find(node => node.name === 'Prepare Existing Registry Decision');
  decision.parameters.jsCode = decision.parameters.jsCode.replace('registry_should_process:\n      shouldProcess,',
    "registry_should_process: $('Discovery Inputs').first().json.new_only ? false : shouldProcess,")
    .replace('registry_decision_reason:\n      reason,',
      "registry_decision_reason: $('Discovery Inputs').first().json.new_only ? 'SKIP_EXISTING_FOR_NEW_DISCOVERY_RUN' : reason,");

  const terminals = ['Final Level 1.1 Validation Summary','Level 1.1 Skip Validation Summary','Fetch Failure Complete',
    'Irrelevant Page Complete','AI Failure Result','Candidate Rejected Result','Candidate API Error Result','Discovery Inputs'];
  for (const name of ['Fetch Failure Complete','Irrelevant Page Complete']) {
    workflow.nodes.push(code(name, 'return $input.all();', [4500,1000]));
  }
  workflow.connections['Successful Fetch?'].main[1] = [edge('Fetch Failure Complete')];
  workflow.connections['Relevant?'].main[1] = [edge('Irrelevant Page Complete')];
  workflow.nodes.push({id:'discovery-completion-barrier',name:'Discovery Completion Barrier',type:'n8n-nodes-base.merge',
    typeVersion:3.2,position:[5000,400],parameters:{mode:'append',numberInputs:8}});
  terminals.forEach((name, index) => {
    const outputs = workflow.connections[name] ||= {main:[[]]};
    outputs.main[0].push(edge('Discovery Completion Barrier',index));
  });
  workflow.nodes.push(code('Discovery Run Summary',fs.readFileSync(path.join(__dirname,'discovery-summary.js'),'utf8'),[5250,400]));
  workflow.connections['Discovery Completion Barrier']={main:[[edge('Discovery Run Summary')]]};
  return workflow;
}

function dashboardDispatcher(binding, discoveryWorkflowId, webhookPath) {
  if (!/^[A-Za-z0-9_-]{5,150}$/.test(webhookPath) || !/^[A-Za-z0-9_-]+$/.test(discoveryWorkflowId)) {
    throw new Error('Configure a fixed discovery workflow ID and webhook path');
  }
  const api = (name, endpoint, jsonBody) => ({id:name.toLowerCase().replace(/\W+/g,'-'),name,
    type:'n8n-nodes-base.httpRequest',typeVersion:4.2,position:[0,0],parameters:{method:'POST',
      url:`=${binding.api_base_url}${endpoint}`,authentication:'genericCredentialType',genericAuthType:'httpHeaderAuth',
      sendHeaders:true,headerParameters:{parameters:[{name:'X-Workspace-ID',value:binding.workspace_id}]},
      sendBody:true,specifyBody:'json',jsonBody,options:{timeout:10000,
        redirect:{redirect:{followRedirects:false}},response:{response:{responseFormat:'json'}}}},
    credentials:{httpHeaderAuth:binding.api_credential}});
  const nodes = [
    {id:'dashboard-webhook',name:'Dashboard Webhook',type:'n8n-nodes-base.webhook',typeVersion:2,
      position:[-500,0],webhookId:webhookPath,parameters:{httpMethod:'POST',path:webhookPath,responseMode:'onReceived',options:{}}},
    code('Validate Dashboard Request',`const body = $json.body;
if (!body || body.workspace_id !== ${JSON.stringify(binding.workspace_id)}
    || !/^[0-9a-f-]{36}$/.test(body.run_id || '')
    || typeof body.run_token !== 'string' || !/^[A-Za-z0-9_-]{32,128}$/.test(body.run_token)) {
  throw new Error('Invalid dashboard discovery request');
}
return [{json:{run_id:body.run_id,run_token:body.run_token,workspace_id:body.workspace_id}}];`,[-250,0]),
    api('Claim Dashboard Run',"/api/discovery/runs/{{ $json.run_id }}/claim",'={{ JSON.stringify({run_token:$json.run_token}) }}'),
    {id:'run-workspace-discovery',name:'Run Workspace Discovery',type:'n8n-nodes-base.executeWorkflow',typeVersion:1.3,
      position:[250,0],parameters:{source:'database',workflowId:{__rl:true,mode:'id',value:discoveryWorkflowId},
        options:{waitForSubWorkflow:true}},onError:'continueRegularOutput',alwaysOutputData:true},
    code('Prepare Dashboard Completion',`const items = $input.all().map(item => item.json);
const valid = items.find(item => item.discovery_summary === true);
const failed = items.some(item => item.error) || !valid;
const request = $('Validate Dashboard Request').first().json;
return [{json:{run_id:request.run_id,run_token:request.run_token,
  status:failed || valid?.status === 'FAILED' ? 'FAILED' : 'COMPLETED',
  summary:valid?.summary || {},error_code:failed ? 'WORKFLOW_FAILED' : (valid?.error_code || null)}}];`,[500,0]),
    api('Complete Dashboard Run',"/api/discovery/runs/{{ $json.run_id }}/complete",'={{ JSON.stringify({run_token:$json.run_token,status:$json.status,summary:$json.summary,error_code:$json.error_code}) }}'),
  ];
  const connections = {};
  for (let i=0;i<nodes.length-1;i++) connections[nodes[i].name]={main:[[edge(nodes[i+1].name)]]};
  return {name:`Dashboard Lead Discovery — ${binding.workspace_id}`,nodes,connections,active:false,
    settings:{executionOrder:'v1',saveDataSuccessExecution:'none',saveDataErrorExecution:'none',saveManualExecutions:false}};
}

module.exports={addDashboardInput,dashboardDispatcher};
