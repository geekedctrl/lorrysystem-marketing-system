#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),path=require('node:path');
const {researchChild}=require('./research-workflows');
const {pipelineChild}=require('./pipeline-workflows');
const {preflightNodes}=require('./bind-workflow');
const {modelSettings}=require('./adapt-discovery');
const read=name=>fs.readFileSync(path.join(__dirname,name),'utf8');
const runtime=read('shared-runtime.js'),research=read('research-runtime.js'),models=read('model-runtime.js');
const usage=read('usage-runtime.js');
const placeholder='00000000-0000-0000-0000-000000000001';
const edge=node=>({node,type:'main',index:0});
const code=(name,jsCode)=>({id:name,name,type:'n8n-nodes-base.code',typeVersion:2,position:[0,0],parameters:{jsCode}});
const gate=(name,expr)=>({id:name,name,type:'n8n-nodes-base.if',typeVersion:2.2,position:[0,0],parameters:{conditions:{options:{caseSensitive:true,typeValidation:'strict',version:2},conditions:[{id:name,leftValue:expr,rightValue:true,operator:{type:'boolean',operation:'true',singleValue:true}}],combinator:'and'},options:{}}});
function binding(input){
  for(const key of ['api_credential','brave_credential'])if(!input[key] || !/^[a-zA-Z0-9_-]+$/.test(input[key].id||'') || !input[key].name || Object.keys(input[key]).some(k=>!['id','name'].includes(k)))throw new Error('Use named n8n credential references');
  if(!input.llm?.credential || !/^[a-zA-Z0-9_-]+$/.test(input.llm.credential.id||'') || !input.llm.credential.name || Object.keys(input.llm.credential).some(k=>!['id','name'].includes(k)))throw new Error('Use a named model credential reference');
  return {...input,workspace_id:placeholder,llm:{...modelSettings(input.llm),credential:input.llm.credential},require_catalog:true};
}
function dynamic(workflow,b,trigger,setup=false){
  const configuration=workflow.nodes.find(n=>n.name==='Workspace Configuration');
  const config={api_base_url:b.api_base_url.replace(/\/$/,''),llm:b.llm,research:{country:'MY',max_pages:6,max_sources:10,max_evidence_chars:24000},require_catalog:!setup,registry_table_id:null};
  configuration.parameters.jsCode=`${runtime}\nconst job=sharedJob($input.first().json); const config=${JSON.stringify(config)};config.shared_job=true;config.job_id=job.job_id;config.workspace_id=job.workspace_id;return [{json:{config,run_input:{...job.input,job_id:job.job_id,kind:job.kind,lease_token:job.lease_token,workspace_id:job.workspace_id}}}];`;
  for(const node of workflow.nodes){
    if(node.type==='n8n-nodes-base.httpRequest' && node.parameters.url.includes("Workspace Configuration")){
      node.credentials={httpHeaderAuth:b.api_credential};node.parameters.headerParameters={parameters:[
        {name:'X-Workspace-ID',value:"={{ $('Workspace Configuration').first().json.config.workspace_id }}"},
        {name:'X-Automation-Lease',value:"={{ $('Workspace Configuration').first().json.run_input.lease_token }}"}]};
    }
  }
  if(trigger==='Research Job Input'){
    const queries=workflow.nodes.find(n=>n.name==='Company Search Queries');
    queries.parameters.jsCode=queries.parameters.jsCode.replace("$('Workspace Configuration').first().json.config.research.country","$('Workspace Guard').first().json.workspace_context.settings.country_code || 'MY'");
    const people=workflow.nodes.find(n=>n.name==='People Search Queries');
    people.parameters.jsCode=people.parameters.jsCode.replace("$('Workspace Configuration').first().json.config.research.country","$('Workspace Guard').first().json.workspace_context.settings.country_code || 'MY'");
  }
  return workflow;
}
function http(b,name,endpoint,options={}){
  return {id:name,name,type:'n8n-nodes-base.httpRequest',typeVersion:4.2,position:[0,0],credentials:{httpHeaderAuth:options.credential||b.api_credential},
    ...(options.soft?{onError:'continueRegularOutput'}:{}),parameters:{method:options.method||'GET',url:options.url||`={{ $('Workspace Configuration').first().json.config.api_base_url }}${endpoint}`,
      authentication:'genericCredentialType',genericAuthType:'httpHeaderAuth',sendHeaders:true,headerParameters:{parameters:options.headers||[]},
      ...(options.body?{sendBody:true,specifyBody:'json',jsonBody:options.body}:{}),...(options.query?{sendQuery:true,queryParameters:{parameters:options.query}}:{}),
      options:{timeout:options.timeout||30000,redirect:{redirect:{followRedirects:false}},response:{response:{responseFormat:'json',fullResponse:!!options.soft,neverError:!!options.soft}}}}};
}
function graph(name,nodes,chains,branches={}){
  const connections={};for(const names of chains)for(let i=0;i<names.length-1;i++)connections[names[i]]={main:[[edge(names[i+1])]]};
  for(const [name,outputs]of Object.entries(branches))connections[name]={main:outputs.map(output=>output.map(edge))};
  nodes.forEach((n,i)=>n.position=[(i%6)*280,Math.floor(i/6)*300]);
  return {name,nodes,connections,active:false,settings:{executionOrder:'v1',executionTimeout:1200,saveDataSuccessExecution:'none',saveDataErrorExecution:'none',saveManualExecutions:false}};
}
function head(b,setup){return [{id:'job-input',name:'Shared Job Input',type:'n8n-nodes-base.executeWorkflowTrigger',typeVersion:1.1,position:[0,0],parameters:{inputSource:'passthrough'}},...preflightNodes({...b,require_catalog:!setup,trigger_nodes:['Shared Job Input']})];}
function setupChild(input){
  const b=binding(input),nodes=head(b,true);
  nodes.push(http(b,'Load Product Setup','/api/automation/job-context'),code('Prepare Product Targeting',`${runtime}\nreturn [{json:{request:setupRequest($json,$('Workspace Configuration').first().json.config.llm)}}];`),
    http(b,'xKiro Product Targeting','',{url:`=${b.llm.base_url}/chat/completions`,credential:b.llm.credential,method:'POST',body:'={{ JSON.stringify($json.request) }}',soft:true,timeout:120000}),
    code('Product Targeting Result',`${runtime}\n${models}\nreturn [{json:setupResult($json,completionContent)}];`));
  return dynamic(graph('Shared Product Setup',nodes,[['Shared Job Input','Workspace Configuration','Load Workspace Context','Workspace Guard','Load Product Setup','Prepare Product Targeting','xKiro Product Targeting','Product Targeting Result']]),b,'Shared Job Input',true);
}
function discoveryChild(input){
  const b=binding(input),nodes=head(b,false);
  nodes.push(http(b,'Load Discovery Memory','/api/automation/memory'),
    http(b,'Search New Companies','',{url:'https://api.search.brave.com/res/v1/web/search',credential:b.brave_credential,soft:true,headers:[{name:'Accept',value:'application/json'}],query:[
      {name:'q',value:"={{ $('Workspace Guard').first().json.query }}"},{name:'country',value:"={{ $('Workspace Guard').first().json.workspace_context.settings.country_code || 'MY' }}"},{name:'count',value:'20'}]}),
    code('Select New Company Pages',`${runtime}\n${research}\nconst job=$('Shared Job Input').first().json;return discoveryPages($json,$('Load Discovery Memory').first().json,job,publicResearchUrl).map(json=>({json}));`),
    gate('Has New Page?','={{ !$json.no_fetch }}'),
    http(b,'Fetch New Company Page','/api/research/fetch-public',{method:'POST',body:'={{ JSON.stringify({url:$json.url}) }}',soft:true,timeout:65000}),
    code('Clean New Company Pages',`${research}\nconst requests=$('Select New Company Pages').all();return $input.all().map((item,index)=>{const request=requests[index].json;const page=cleanResearchPage(item.json,request,{company:{domain:request.domain}});return {json:{...page,domain:publicResearchUrl(page.url)?.host||request.domain},pairedItem:{item:index}};});`),
    code('Prepare Discovery Extraction',`${runtime}\nconst pages=$input.all().map(i=>i.json).filter(p=>!p.failed && p.evidence);const workspace=$('Workspace Guard').first().json;return [{json:{pages,no_pages:!pages.length,request:discoveryRequest(pages,workspace.workspace_context,$('Workspace Configuration').first().json.config.llm,workspace.query)}}];`),
    gate('Has Fetched Evidence?','={{ !$json.no_pages }}'),
    http(b,'xKiro Discovery Extraction','',{url:`=${b.llm.base_url}/chat/completions`,credential:b.llm.credential,method:'POST',body:'={{ JSON.stringify($json.request) }}',soft:true,timeout:120000}),
    code('Validate Discovered Companies',`${runtime}\n${models}\nreturn discoveryResults($json,$('Prepare Discovery Extraction').first().json.pages,$('Workspace Guard').first().json.workspace_context,$('Shared Job Input').first().json,completionContent).map(json=>({json}));`),
    gate('Has Suitable Company?','={{ !$json.no_candidate }}'),
    http(b,'Accept Sourced Company','/api/automation/candidates',{method:'POST',body:'={{ JSON.stringify($json.candidate) }}'}),
    code('Discovery Batch Result',"return [{json:{shared_outcome:'COMPLETED',output:{accepted:$input.all().filter(i=>i.json.outcome==='ACCEPTED').length}}}];"),
    code('Empty Discovery Result',"return [{json:{shared_outcome:$json.search_failed?'FAILED':'COMPLETED',...($json.search_failed?{failure_reason:'SEARCH_FAILED'}:{}),output:{accepted:0}}}];"),
    code('Discovery Validation Result','return [{json:$json}];'));
  const result=graph('Shared Company Discovery',nodes,[
    ['Shared Job Input','Workspace Configuration','Load Workspace Context','Workspace Guard','Load Discovery Memory','Search New Companies','Select New Company Pages','Has New Page?'],
    ['Fetch New Company Page','Clean New Company Pages','Prepare Discovery Extraction','Has Fetched Evidence?'],
    ['xKiro Discovery Extraction','Validate Discovered Companies','Has Suitable Company?'],['Accept Sourced Company','Discovery Batch Result']
  ],{'Has New Page?':[['Fetch New Company Page'],['Empty Discovery Result']],'Has Fetched Evidence?':[['xKiro Discovery Extraction'],['Empty Discovery Result']],'Has Suitable Company?':[['Accept Sourced Company'],['Discovery Validation Result']]});
  return dynamic(result,b,'Shared Job Input');
}
function sharedChildren(input){
  const b=binding(input);
  const children={setup:setupChild(input),discovery:discoveryChild(input),research:dynamic({...researchChild(b),name:'Shared Company and People Research'},b,'Research Job Input'),pipeline:dynamic({...pipelineChild(b),name:'Shared Qualification and Outreach Preparation'},b,'Stage Job Input')};
  const results={setup:['Product Targeting Result'],discovery:['Discovery Batch Result','Empty Discovery Result','Discovery Validation Result'],research:['Research Result','Research Failure Result','No Research Evidence'],pipeline:['Stage Result','Stage Validation Failed']};
  for(const [key,workflow] of Object.entries(children))for(const node of workflow.nodes)if(results[key].includes(node.name)) {
    node.parameters.jsCode=`${usage}\nconst result=(function(){${node.parameters.jsCode}\n})();return result.map(item=>({...item,json:{...item.json,usage:workflowUsage($)}}));`;
  }
  return children;
}
function sharedWorker(input,ids){
  const b=binding(input);for(const key of ['setup','discovery','research','pipeline'])if(!/^[a-zA-Z0-9_-]+$/.test(ids[key]||''))throw new Error('Set all four fixed shared child IDs');
  const control=(name,endpoint,options={})=>http(b,name,endpoint,{...options,url:b.api_base_url.replace(/\/$/,'')+endpoint});
  const nodes=[{id:'schedule',name:'Shared Worker Schedule',type:'n8n-nodes-base.scheduleTrigger',typeVersion:1.2,position:[0,0],parameters:{rule:{interval:[{field:'minutes',minutesInterval:1}]}}},
    control('Shared API Health','/api/automation/worker/health',{soft:true}),gate('Shared API Ready?','={{ $json.statusCode === 200 && $json.body?.shared_automation_version === 1 }}'),
    code('Shared Worker Waiting',"if(![404,405].includes($json.statusCode))throw new Error('Shared worker credential rejected');return [{json:{worker_status:'WAITING_API_DEPLOYMENT'}}];"),
    control('Claim Shared Job','/api/automation/worker/claim',{method:'POST'}),gate('Shared Job Claimed?','={{ !!$json.job_id }}'),code('Validate Claimed Job',`${runtime}\nreturn [{json:sharedJob($json)}];`),
    gate('Is Product Setup?','={{ $json.kind === "SETUP" }}'),gate('Is Discovery?','={{ $json.kind === "DISCOVERY" }}'),gate('Is Research?','={{ $json.kind === "RESEARCH" }}')];
  for(const key of Object.keys(ids))nodes.push({id:'run-'+key,name:'Run Shared '+key,type:'n8n-nodes-base.executeWorkflow',typeVersion:1.3,position:[0,0],parameters:{source:'database',workflowId:{__rl:true,mode:'id',value:ids[key]},options:{waitForSubWorkflow:true}},onError:'continueRegularOutput',alwaysOutputData:true});
  nodes.push(code('Finish Shared Job Input',`const job=$('Validate Claimed Job').first().json;const results=$input.all().map(i=>i.json);const result=results.find(r=>r.shared_outcome || (r.research_id===job.input.research_id && r.lead_id===job.input.lead_id && ['COMPLETED','PARTIAL','FAILED'].includes(r.research_outcome)) || (r.id===job.input.id && r.lead_id===job.input.lead_id && ['COMPLETED','FAILED'].includes(r.pipeline_outcome)));const outcome=result?.shared_outcome||result?.research_outcome||result?.pipeline_outcome;const failed=!['COMPLETED','PARTIAL'].includes(outcome);return [{json:{job_id:job.job_id,lease_token:job.lease_token,output:result?.output||{},...(failed?{failure_reason:/^[A-Z0-9_]{1,80}$/.test(result?.failure_reason||'')?result.failure_reason:'SHARED_WORKFLOW_FAILED'}:{})}}];`),
    control('Finish Shared Job','/api/automation/worker/finish',{method:'POST',body:'={{ JSON.stringify($json) }}',timeout:60000}));
  const finisher=nodes.find(node=>node.name==='Finish Shared Job Input');
  finisher.parameters.jsCode=finisher.parameters.jsCode.replace('output:result?.output||{},',"output:result?.output||{},...($('Shared API Health').first().json.body?.automation_metrics_version===1 && result?.usage ? {usage:result.usage}:{}),");
  return graph('Shared Product Automation Queue',nodes,[['Shared Worker Schedule','Shared API Health','Shared API Ready?'],['Claim Shared Job','Shared Job Claimed?'],['Validate Claimed Job','Is Product Setup?'],...Object.keys(ids).map(key=>['Run Shared '+key,'Finish Shared Job Input','Finish Shared Job'])],
    {'Shared API Ready?':[['Claim Shared Job'],['Shared Worker Waiting']],'Shared Job Claimed?':[['Validate Claimed Job'],[]],'Is Product Setup?':[['Run Shared setup'],['Is Discovery?']],'Is Discovery?':[['Run Shared discovery'],['Is Research?']],'Is Research?':[['Run Shared research'],['Run Shared pipeline']]});
}
module.exports={sharedChildren,sharedWorker};
if(require.main===module){try{const [mode,source,out,ids]=process.argv.slice(2);const input=JSON.parse(fs.readFileSync(source,'utf8'));const result=mode==='children'?sharedChildren(input):mode==='worker'?sharedWorker(input,JSON.parse(fs.readFileSync(ids,'utf8'))):null;if(!result)throw new Error('Usage: shared-workflows.js children|worker BINDING OUTPUT [CHILD_IDS]');fs.writeFileSync(out,JSON.stringify(result,null,2)+'\n',{flag:'wx'});console.log('Created shared automation workflows without secrets.');}catch(error){console.error(error.message);process.exitCode=1;}}
