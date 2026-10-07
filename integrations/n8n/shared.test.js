'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const {sharedChildren,sharedWorker}=require('./shared-workflows');
const {sharedJob,setupResult,discoveryPages,discoveryResults}=require('./shared-runtime');
const {completionContent}=require('./model-runtime');
const {publicResearchUrl}=require('./research-runtime');
const {assertWorkspaceContext}=require('./workspace-runtime');
const A='00000000-0000-0000-0000-000000000001',B='00000000-0000-0000-0000-000000000002',J='10000000-0000-0000-0000-000000000001';
const credential={id:'worker-ref',name:'Shared worker'};
const binding={api_base_url:'http://marketing-api:8000',api_credential:credential,brave_credential:{id:'brave-ref',name:'Brave'},llm:{base_url:'https://api.xkiro.com/v1',provider:'xkiro',model:'mistralai/mistral-large-2512',max_tokens:6000,credential:{id:'model-ref',name:'xKiro'}}};
const job=(wid=A)=>({job_id:J,kind:'DISCOVERY',workspace_id:wid,lease_token:'fixture-token-'.repeat(4),input:{workspace_id:wid,target_new_companies:1,query:'Business software buyers Malaysia'}});
const envelope=value=>({choices:[{finish_reason:'stop',message:{content:JSON.stringify(value)}}]});
function context(wid=A){return {workspace:{id:wid,role:'SERVICE',name:wid===A?'Fleet':'Accounting'},automation:{contract_version:1,credential_kind:'job',job_id:J,registry_namespace:`workspace:${wid}:discovery`,human_candidate_review_required:false,human_marketing_approval_required:true},icps:[{id:wid+'-icp',code:'AUTO_1',name:'Target customers'}],products:[{id:wid+'-product',code:'PRODUCT_MAIN',name:'Offering'}]};}
test('same generated child graphs receive two unrelated workspaces and exact job contexts',()=>{
  const graphs=sharedChildren(binding);
  for(const graph of Object.values(graphs))for(const wid of [A,B]){
    const node=graph.nodes.find(n=>n.name==='Workspace Configuration');
    const input=job(wid);input.kind=graph.name.includes('Setup')?'SETUP':input.kind;
    const [item]=vm.runInNewContext('(function(){'+node.parameters.jsCode+'})()',{$input:{first:()=>({json:input})}});
    assert.equal(item.json.config.workspace_id,wid);assert.equal(item.json.config.job_id,J);assert.equal(item.json.run_input.lease_token,input.lease_token);
    assert.equal(assertWorkspaceContext(context(wid),item.json.config).workspace_name,wid===A?'Fleet':'Accounting');
    assert.throws(()=>assertWorkspaceContext(context(wid===A?B:A),item.json.config),/match/);
    assert.throws(()=>assertWorkspaceContext({...context(wid),automation:{...context(wid).automation,job_id:B}},item.json.config),/contract/);
  }
});
test('every business request has dynamic lease/workspace headers; providers retain named credentials; no sending or execution retention',()=>{
  for(const graph of Object.values(sharedChildren(binding))){
    assert.equal(graph.settings.saveDataSuccessExecution,'none');assert.equal(graph.settings.saveDataErrorExecution,'none');
    for(const node of graph.nodes){
      assert.doesNotMatch(node.type,/emailSend|gmail|outlook|linkedIn/);
      if(node.type==='n8n-nodes-base.httpRequest' && node.parameters.url.includes('Workspace Configuration')){
        assert.deepEqual(node.credentials.httpHeaderAuth,credential);
        const headers=node.parameters.headerParameters.parameters;assert.equal(headers.length,2);assert.equal(headers[0].name,'X-Workspace-ID');assert.match(headers[0].value,/config.workspace_id/);assert.equal(headers[1].name,'X-Automation-Lease');assert.match(headers[1].value,/run_input.lease_token/);
      }
      if(node.type==='n8n-nodes-base.code')new Function(node.parameters.jsCode);
    }
  }
  const worker=sharedWorker(binding,{setup:'s',discovery:'d',research:'r',pipeline:'p'});
  assert.equal(worker.nodes.filter(n=>n.type==='n8n-nodes-base.executeWorkflow').length,4);
  assert.equal(worker.settings.saveDataErrorExecution,'none');
  assert.throws(()=>sharedWorker(binding,{setup:'s'}),/four/);
  assert.throws(()=>sharedChildren({...binding,api_credential:{...credential,value:'secret'}}),/references/);
});
test('job envelope rejects missing proof, wrong input identity and unknown stages',()=>{
  sharedJob(job());for(const bad of [{...job(),lease_token:''},{...job(),kind:'SENDING'},{...job(),input:{workspace_id:B}}])assert.throws(()=>sharedJob(bad),/envelope/);
});
test('setup requires bounded valid targeting and sanitizes provider failures',()=>{
  const output={discovery_query:'Business software Malaysia',icps:[{name:'Professional companies',description:'Companies needing supported business software capabilities'}]};
  assert.equal(setupResult(envelope(output),completionContent).shared_outcome,'COMPLETED');
  assert.equal(setupResult(envelope({...output,api_key:'secret'}),completionContent).shared_outcome,'FAILED');
  const failure=setupResult({statusCode:503,body:{error:'PRIVATE_PROVIDER_KEY'}},completionContent);assert.equal(failure.failure_reason,'AI_PROVIDER_HTTP_503');assert.doesNotMatch(JSON.stringify(failure),/PRIVATE/);
});
test('search uses workspace memory and bounded fetched official sources; hallucinations and foreign ICPs cannot become leads',()=>{
  const response={web:{results:[{url:'https://old.com/'},{url:'https://new.com/'},{url:'https://new.com/about'},{url:'https://linkedin.com/in/person'},{url:'http://127.0.0.1/'}]}};
  assert.equal(discoveryPages(response,{domains:['old.com']},job(),publicResearchUrl).length,1);
  const quote='New Company provides business services to professional teams across Malaysia.';
  const pages=[{url:'https://new.com/',domain:'new.com',title:'New Company',evidence:quote}];
  const ws=assertWorkspaceContext(context(),{workspace_id:A,job_id:J,shared_job:true});
  const candidate={company_name:'New Company',source_url:pages[0].url,evidence_quote:quote,icp_code:'AUTO_1',icp_confidence:.85,icp_reasoning:'These services support the documented ICP fit.',company_identity_verified:true};
  const [result]=discoveryResults(envelope({candidates:[candidate,candidate]}),pages,ws,job(),completionContent);
  assert.equal(result.candidate.suggested_icp_profile_id,A+'-icp');assert.equal(result.candidate.source.source_type,'COMPANY_WEBSITE');assert.equal(result.candidate.source.evidence,quote);
  for(const bad of [null,[],{...candidate,evidence_quote:'Invented company and capabilities unrelated to the public page.'},{...candidate,icp_code:'FOREIGN'},{...candidate,icp_confidence:.4},{...candidate,company_identity_verified:false}])assert.equal(discoveryResults(envelope({candidates:[bad]}),pages,ws,job(),completionContent)[0].no_candidate,true);
});
test('guarded redirects use the fetched company domain for acceptance and discovery memory',()=>{
  const node=sharedChildren(binding).discovery.nodes.find(n=>n.name==='Clean New Company Pages');
  const input={json:{fetch_status:'SUCCESS',final_url:'https://newcompany.com/',body:'<html>New Company provides professional business services in Malaysia. Jane Tan is its operations manager and public business contact.</html>'}};
  const result=vm.runInNewContext('(function(){'+node.parameters.jsCode+'})()',{$input:{all:()=>[input]},$:()=>({all:()=>[{json:{url:'https://oldcompany.com/',domain:'oldcompany.com'}}]})});
  assert.equal(result[0].json.domain,'newcompany.com');assert.equal(result[0].json.url,'https://newcompany.com/');
});

test('setup and discovery accept fenced JSON while rejecting prose and invalid schemas',()=>{
  const response=content=>({choices:[{finish_reason:'stop',message:{content}}]});
  const output={discovery_query:'Logistics fleets Malaysia',icps:[{name:'Transport operators',description:'Commercial vehicle operators needing supported fleet solutions'}]};
  assert.equal(setupResult(response('  ```json\n'+JSON.stringify(output)+'\n```  '),completionContent).shared_outcome,'COMPLETED');
  assert.equal(setupResult(response('Here is the answer: '+JSON.stringify(output)),completionContent).shared_outcome,'FAILED');
  assert.equal(setupResult(response('```json\n'+JSON.stringify({...output,sending:true})+'\n```'),completionContent).shared_outcome,'FAILED');
  const result=discoveryResults(response('```json\n{"candidates":[]}\n```'),[],{},job(),completionContent);
  assert.equal(result[0].shared_outcome,'COMPLETED');
});

test('shared discovery declares the Accept header required by Brave Search',()=>{
 const search=sharedChildren(binding).discovery.nodes.find(n=>n.name==='Search New Companies');
 assert.equal(search.parameters.sendHeaders,true);
 assert.ok(search.parameters.headerParameters.parameters.some(h=>h.name==='Accept' && h.value==='application/json'));
 assert.deepEqual(search.credentials.httpHeaderAuth,binding.brave_credential);
});
