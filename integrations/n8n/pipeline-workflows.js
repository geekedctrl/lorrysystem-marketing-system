#!/usr/bin/env node
'use strict';
const fs=require('node:fs');
const path=require('node:path');
const {preflightNodes}=require('./bind-workflow');
const {modelSettings}=require('./adapt-discovery');
const runtime=fs.readFileSync(path.join(__dirname,'pipeline-runtime.js'),'utf8');
const workspaceRuntime=fs.readFileSync(path.join(__dirname,'workspace-runtime.js'),'utf8');
const modelRuntime=fs.readFileSync(path.join(__dirname,'model-runtime.js'),'utf8');
const edge=node=>({node,type:'main',index:0});
const code=(name,jsCode)=>({id:name.toLowerCase().replace(/\W+/g,'-'),name,type:'n8n-nodes-base.code',typeVersion:2,position:[0,0],parameters:{jsCode}});
function gate(name,expression){return {id:name,name,type:'n8n-nodes-base.if',typeVersion:2.2,position:[0,0],parameters:{conditions:{options:{caseSensitive:true,leftValue:'',typeValidation:'strict',version:2},conditions:[{id:'condition',leftValue:expression,rightValue:true,operator:{type:'boolean',operation:'true',singleValue:true}}],combinator:'and'},options:{}}};}
function http(binding,name,endpoint,options={}) {
  const {model=false,method='GET',body,soft=false}=options;
  const credential=model?binding.llm.credential:binding.api_credential;
  return {id:name,name,type:'n8n-nodes-base.httpRequest',typeVersion:4.2,position:[0,0],credentials:{httpHeaderAuth:credential},
    ...(soft?{onError:'continueRegularOutput'}:{}),parameters:{method,
      url:model?`=${binding.llm.base_url}/chat/completions`:`={{ $('Workspace Configuration').first().json.config.api_base_url }}${endpoint}`,
      authentication:'genericCredentialType',genericAuthType:'httpHeaderAuth',sendHeaders:true,headerParameters:{parameters:model?[]:[{name:'X-Workspace-ID',value:binding.workspace_id}]},
      ...(body?{sendBody:true,specifyBody:'json',jsonBody:body}:{}),options:{timeout:model?120000:20000,
        redirect:{redirect:{followRedirects:false}},response:{response:{responseFormat:'json',fullResponse:soft,neverError:soft}}}}};
}
function setup(binding,trigger){
  if(binding.require_catalog===false)throw new Error('Pipeline requires current workspace catalogs');
  const credential=binding.llm?.credential;
  if(!credential || !/^[a-zA-Z0-9_-]+$/.test(credential.id||'') || typeof credential.name!=='string' || !credential.name.trim() || Object.keys(credential).some(k=>!['id','name'].includes(k)))throw new Error('Set an n8n model credential reference');
  const normalized={...binding,llm:modelSettings(binding.llm),require_catalog:true,trigger_nodes:[trigger]};
  return {binding:{...normalized,llm:{...normalized.llm,credential}},nodes:preflightNodes(normalized)};
}
function finish(name,nodes,connections){nodes.forEach((n,i)=>n.position=[(i%6)*280,Math.floor(i/6)*300]);return {name,nodes,connections,active:false,settings:{executionOrder:'v1',executionTimeout:300,saveDataSuccessExecution:'none',saveDataErrorExecution:'none',saveManualExecutions:false}};}
function pipelineChild(input){
  const {binding,nodes:preflight}=setup(input,'Stage Job Input');
  const nodes=[{id:'stage-job-input',name:'Stage Job Input',type:'n8n-nodes-base.executeWorkflowTrigger',typeVersion:1.1,position:[0,0],parameters:{inputSource:'passthrough'}},...preflight,
    http(binding,'Load Stage Context','/api/pipeline/{{ $json.id }}/context'),
    code('Prepare Stage Model',`${runtime}\n${workspaceRuntime}\nconst job=$('Workspace Guard').first().json;
const workspace=job.workspace_context;
const context=validatePipelineContext($json,job,workspace);
return [{json:preparePipelineModel(context,workspace,$('Workspace Configuration').first().json.config.llm,workspacePrompt)}];`),
    http(binding,'xKiro Stage Extraction','',{model:true,method:'POST',body:'={{ JSON.stringify($json.request) }}',soft:true}),
    code('Validate Stage Output',`${runtime}\n${modelRuntime}\nreturn [{json:validatePipelineOutput($json,$('Workspace Guard').first().json,$('Load Stage Context').first().json,completionContent)}];`),
    gate('Stage Output Valid?','={{ $json.pipeline_outcome === "VALID" }}'),
    code('Stage Validation Failed','return [{json:$json}];'),
    http(binding,'Complete Stage','/api/pipeline/{{ $json.id }}/complete',{method:'PATCH',body:'={{ JSON.stringify({output:$json.output}) }}'}),
    code('Stage Result',"const expected=$('Workspace Guard').first().json; if ($json.id!==expected.id || $json.status!=='COMPLETED') throw new Error('Stage completion mismatch'); return [{json:{id:expected.id,lead_id:expected.lead_id,pipeline_outcome:'COMPLETED'}}];")];
  const connections={};
  const chain=(...names)=>names.slice(0,-1).forEach((n,i)=>connections[n]={main:[[edge(names[i+1])]]});
  chain('Stage Job Input','Workspace Configuration','Load Workspace Context','Workspace Guard','Load Stage Context','Prepare Stage Model','xKiro Stage Extraction','Validate Stage Output','Stage Output Valid?');
  connections['Stage Output Valid?']={main:[[edge('Complete Stage')],[edge('Stage Validation Failed')]]};
  chain('Complete Stage','Stage Result');
  return finish(`Workspace Lead Stages — ${binding.workspace_id}`,nodes,connections);
}
function pipelineWorker(input,childId){
  if(!/^[a-zA-Z0-9_-]+$/.test(childId||''))throw new Error('Set a fixed stage child workflow ID');
  const {binding,nodes:preflight}=setup(input,'Stage Schedule');
  const nodes=[{id:'stage-schedule',name:'Stage Schedule',type:'n8n-nodes-base.scheduleTrigger',typeVersion:1.2,position:[0,0],parameters:{rule:{interval:[{field:'minutes',minutesInterval:1}]}}},...preflight,
    http(binding,'Stage API Health','/api/pipeline/health',{soft:true}),
    gate('Stage API Ready?','={{ $json.statusCode === 200 && $json.body?.pipeline_version === 1 }}'),
    code('Wait for Stage API',"if (![404,405].includes($json.statusCode)) throw new Error('Stage API preflight rejected'); return [{json:{worker_status:'WAITING_API_DEPLOYMENT'}}];"),
    http(binding,'Claim Stage','/api/pipeline/claim',{method:'POST'}),
    gate('Stage Claimed?','={{ !!$json.id }}'),
    code('Prepare Claimed Stage',`if($json.status!=='RUNNING'||$json.workspace_id!==${JSON.stringify(binding.workspace_id)})throw new Error('Wrong claimed workspace stage');return [{json:$json}];`),
    {id:'run-stage',name:'Run Lead Stage',type:'n8n-nodes-base.executeWorkflow',typeVersion:1.3,position:[0,0],parameters:{source:'database',workflowId:{__rl:true,mode:'id',value:childId},options:{waitForSubWorkflow:true}},onError:'continueRegularOutput',alwaysOutputData:true},
    code('Check Stage Outcome',`const job=$('Prepare Claimed Stage').first().json;
const result=$input.all().map(i=>i.json).find(r=>r.id===job.id&&r.lead_id===job.lead_id&&['COMPLETED','FAILED'].includes(r.pipeline_outcome));
const reason=result?.failure_reason;
return [{json:{id:job.id,pipeline_outcome:result?.pipeline_outcome||'FAILED',failure_reason:typeof reason==='string'&&/^[A-Z0-9_]{1,80}$/.test(reason)?reason:'STAGE_WORKFLOW_FAILED'}}];`),
    gate('Stage Failed?','={{ $json.pipeline_outcome === "FAILED" }}'),
    http(binding,'Fail Stage','/api/pipeline/{{ $json.id }}/fail',{method:'PATCH',body:'={{ JSON.stringify({reason:$json.failure_reason}) }}'})];
  const connections={};const chain=(...names)=>names.slice(0,-1).forEach((n,i)=>connections[n]={main:[[edge(names[i+1])]]});
  chain('Stage Schedule','Workspace Configuration','Load Workspace Context','Workspace Guard','Stage API Health','Stage API Ready?');
  connections['Stage API Ready?']={main:[[edge('Claim Stage')],[edge('Wait for Stage API')]]};chain('Claim Stage','Stage Claimed?');
  connections['Stage Claimed?']={main:[[edge('Prepare Claimed Stage')],[]]};chain('Prepare Claimed Stage','Run Lead Stage','Check Stage Outcome','Stage Failed?');
  connections['Stage Failed?']={main:[[edge('Fail Stage')],[]]};
  const result=finish(`Workspace Lead Stage Queue — ${binding.workspace_id}`,nodes,connections);result.settings.executionTimeout=360;return result;
}
module.exports={pipelineChild,pipelineWorker};
if(require.main===module){try{const [mode,bindingPath,output,childId]=process.argv.slice(2);if(!['child','worker'].includes(mode)||!bindingPath||!output)throw new Error('Usage: node pipeline-workflows.js child|worker BINDING.json OUTPUT.json [CHILD_ID]');const binding=JSON.parse(fs.readFileSync(bindingPath,'utf8'));fs.writeFileSync(output,JSON.stringify(mode==='child'?pipelineChild(binding):pipelineWorker(binding,childId),null,2)+'\n',{flag:'wx'});console.log('Created inactive workspace lead stage workflow.');}catch(error){console.error(error.message);process.exitCode=1;}}
