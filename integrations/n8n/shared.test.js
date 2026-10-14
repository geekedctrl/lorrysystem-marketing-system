'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const {sharedChildren,sharedWorker}=require('./shared-workflows');
const {sharedJob,setupResult,discoverySearch,discoveryPages,discoveryEvidence,discoveryRequest,discoveryResults}=require('./shared-runtime');
const {completionContent}=require('./model-runtime');
const {publicResearchUrl}=require('./research-runtime');
const {assertWorkspaceContext}=require('./workspace-runtime');
const A='00000000-0000-0000-0000-000000000001',B='00000000-0000-0000-0000-000000000002',J='10000000-0000-0000-0000-000000000001';
const credential={id:'worker-ref',name:'Shared worker'};
const binding={api_base_url:'http://marketing-api:8000',api_credential:credential,brave_credential:{id:'brave-ref',name:'Brave'},llm:{base_url:'https://api.xkiro.com/v1',provider:'xkiro',model:'mistralai/mistral-large-2512',max_tokens:6000,credential:{id:'model-ref',name:'xKiro'}}};
const job=(wid=A)=>({job_id:J,kind:'DISCOVERY',workspace_id:wid,lease_token:'fixture-token-'.repeat(4),input:{workspace_id:wid,target_new_companies:1,query:'Business software buyers Malaysia'}});
const envelope=value=>({choices:[{finish_reason:'stop',message:{content:JSON.stringify(value)}}]});
function context(wid=A){return {workspace:{id:wid,role:'SERVICE',name:wid===A?'Fleet':'Accounting'},automation:{contract_version:1,credential_kind:'job',job_id:J,registry_namespace:`workspace:${wid}:discovery`,human_candidate_review_required:true,human_marketing_approval_required:true},icps:[{id:wid+'-icp',code:'AUTO_1',name:'Target customers'}],products:[{id:wid+'-product',code:'PRODUCT_MAIN',name:'Offering'}]};}
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
    assert.throws(()=>assertWorkspaceContext({...context(wid),automation:{...context(wid).automation,human_candidate_review_required:false}},item.json.config),/contract/);
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
  const guarded=sharedWorker({...binding,workspace_id:A,ownership_api_base_url:'http://native:8000',ownership_credential:credential},{setup:'s',discovery:'d',research:'r',pipeline:'p'});
  assert.ok(guarded.nodes.some(n=>n.name==='Executor Ownership Preflight'));
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

test('directories cannot consume the company fetch budget; official homepages rank ahead of product articles',()=>{
  const results=[
    {url:'https://ensun.io/search/fleet-management/malaysia'},
    {url:'https://www.goodfirms.co/logistics'},
    {url:'https://motawill.com/top-10-logistics-companies-in-malaysia/',title:'Top 10 logistics companies'},
    {url:'https://vendor.com/products/fleet-software'},
    {url:'https://old.com/'},
    {url:'https://new.com/',title:'New Company Logistics'},
    {url:'https://new.com/services'},
    {url:'https://linkedin.com/company/test'},
  ];
  const pages=discoveryPages({web:{results}},{domains:['old.com']},job(),publicResearchUrl);
  assert.deepEqual(pages.map(p=>p.domain),['new.com','vendor.com']);
  assert.equal(pages[0].url,'https://new.com/');
});

test('search excludes this workspace memory and stays bounded without inserting unsafe operators',()=>{
  const a=discoverySearch(job(A),{domains:['old.com','www.OLD.com','bad.com OR site:private.test']});
  const b=discoverySearch(job(B),{domains:['other.com']});
  assert.match(a.query,/official company website/);assert.match(a.query,/-site:old.com/);
  assert.equal(a.query.match(/-site:old.com/g).length,1);
  assert.doesNotMatch(a.query,/private|other.com/);assert.doesNotMatch(b.query,/old.com/);
  assert.match(b.query,/-site:other.com/);
  const long=discoverySearch({...job(),input:{...job().input,query:'a '.repeat(149)}},{domains:Array.from({length:10000},(_,i)=>`company${i}.com`)});
  assert.ok(long.query.length<=400);assert.ok(long.query.split(/\s+/).length<=50);
});

test('search preparation is wired before Brave, and unreadable websites fail instead of reporting no matches',()=>{
  const workflow=sharedChildren(binding).discovery;
  assert.equal(workflow.connections['Load Discovery Memory'].main[0][0].node,'Prepare Company Search');
  assert.equal(workflow.connections['Prepare Company Search'].main[0][0].node,'Search New Companies');
  const prepare=workflow.nodes.find(n=>n.name==='Prepare Discovery Extraction');
  const inputs=[{json:{failed:true,failure_reason:'HTTP_403'}}];
  const [item]=vm.runInNewContext('(function(){'+prepare.parameters.jsCode+'})()',{
    $input:{all:()=>inputs},$:name=>({first:()=>({json:name==='Workspace Guard'?{query:'example',workspace_context:{}}:{config:{llm:{model:'fixture',max_tokens:100}}}})})
  });
  assert.equal(item.json.failure_reason,'DISCOVERY_FETCH_FAILED');
  const empty=workflow.nodes.find(n=>n.name==='Empty Discovery Result');
  const run=json=>vm.runInNewContext('(function(){'+empty.parameters.jsCode+'})()',{$json:json,$:()=>({all:()=>[]})})[0].json;
  assert.equal(run(item.json).shared_outcome,'FAILED');
  assert.equal(run(item.json).failure_reason,'DISCOVERY_FETCH_FAILED');
  assert.equal(run({no_fetch:true}).shared_outcome,'COMPLETED');
  assert.equal(run({search_failed:true}).failure_reason,'SEARCH_FAILED');
});

test('selected excerpt IDs preserve exact fetched evidence instead of model-combined passages',()=>{
  const quote='New Company provides industrial haulage services across Malaysia. Mission: deliver safely. Vision: grow carefully. Its fleet includes public transport equipment.';
  const pages=[{url:'https://new.com/',domain:'new.com',title:'New Company',evidence:quote}];
  const ws=assertWorkspaceContext(context(),{workspace_id:A,job_id:J,shared_job:true});
  const candidate={company_name:'New Company',source_id:'P1',excerpt_id:'P1_E1',icp_code:'AUTO_1',icp_confidence:.85,icp_reasoning:'The excerpt documents industrial transport operations.',company_identity_verified:true,
    source_url:'https://invented.com/',evidence_quote:'New Company guarantees unreal savings.'};
  const [result]=discoveryResults(envelope({candidates:[candidate]}),pages,ws,job(),completionContent);
  assert.equal(result.candidate.website_url,pages[0].url);
  assert.equal(result.candidate.source_summary,quote);
  assert.ok(pages[0].evidence.includes(result.candidate.source_summary));
  assert.doesNotMatch(result.candidate.source_summary,/guarantees/);
  const request=discoveryRequest(pages,ws,binding.llm,job().input.query);
  assert.equal(JSON.parse(request.messages[1].content)[0].excerpts[0].text,quote);
  assert.match(request.messages[0].content,/Do not write an evidence quote or URL/);
});

test('invented or cross-page excerpt IDs and unsupported identity/ICP cannot create companies',()=>{
  const pages=[{url:'https://new.com/',domain:'new.com',evidence:'New Company provides industrial haulage services across Malaysia.'},
    {url:'https://other.com/',domain:'other.com',evidence:'Other Company provides accounting services across Malaysia.'}];
  const ws=assertWorkspaceContext(context(),{workspace_id:A,job_id:J,shared_job:true});
  const c={company_name:'New Company',source_id:'P1',excerpt_id:'P1_E1',icp_code:'AUTO_1',icp_confidence:.85,icp_reasoning:'Industrial transport operations are documented.',company_identity_verified:true};
  for(const bad of [{...c,source_id:'FOREIGN'},{...c,excerpt_id:'P2_E1'},{...c,excerpt_id:'P1_E99'},
    {...c,company_name:'Invented Company'},{...c,icp_code:'__proto__'},{...c,icp_code:'FOREIGN'},
    {...c,company_identity_verified:false},{...c,icp_confidence:.5}]){
    assert.equal(discoveryResults(envelope({candidates:[bad]}),pages,ws,job(),completionContent)[0].failure_reason,'DISCOVERY_EVIDENCE_REJECTED');
  }
});

test('excerpt windows overlap and stay within source and persisted quotation bounds',()=>{
  const text='New Company transport services. '+'z'.repeat(9000);
  const [source]=discoveryEvidence([{url:'https://new.com/',evidence:text}]);
  assert.equal(source.excerpts.length,8);
  for(const e of source.excerpts){assert.ok(e.text.length<=1000);assert.ok(text.includes(e.text));}
  assert.equal(source.excerpts[0].text.slice(800),source.excerpts[1].text.slice(0,200));
});

test('rejected model candidates fail visibly; an empty assessment remains a valid no-match result',()=>{
  const quote='Trading and Transport Sdn Bhd provides industrial transport services across Malaysia.';
  const pages=[{url:'https://new.com/',domain:'new.com',evidence:quote}];
  const ws={icp_ids:{AUTO_1:A+'-icp'}};
  const candidate={company_name:'Trading & Transport Sdn Bhd',source_url:pages[0].url,evidence_quote:quote,icp_code:'AUTO_1',icp_confidence:.85,icp_reasoning:'Source confirms the business transport services.',company_identity_verified:true};
  const rejected=discoveryResults(envelope({candidates:[candidate]}),pages,ws,job(),completionContent)[0];
  assert.equal(rejected.shared_outcome,'FAILED');
  assert.equal(rejected.failure_reason,'DISCOVERY_EVIDENCE_REJECTED');
  assert.equal(discoveryResults(envelope({candidates:[]}),pages,ws,job(),completionContent)[0].shared_outcome,'COMPLETED');
  const valid=discoveryResults(envelope({candidates:[{...candidate,company_name:'Trading and Transport Sdn Bhd'}]}),pages,ws,job(),completionContent)[0];
  assert.equal(valid.candidate.company_name,'Trading and Transport Sdn Bhd');
});

test('visible HTML punctuation is decoded before extraction without weakening exact quotation checks',()=>{
  const node=sharedChildren(binding).discovery.nodes.find(n=>n.name==='Clean New Company Pages');
  const input={json:{fetch_status:'SUCCESS',final_url:'https://new.com/',body:'<html><title>New Company</title><p>New Company is Johor&rsquo;s transport operator &mdash; serving Malaysia with industrial transport and warehousing services.</p></html>'}};
  const page=vm.runInNewContext('(function(){'+node.parameters.jsCode+'})()',{$input:{all:()=>[input]},$:()=>({all:()=>[{json:{url:'https://new.com/',domain:'new.com'}}]})})[0].json;
  const quote='New Company is Johor\u2019s transport operator \u2014 serving Malaysia with industrial transport and warehousing services.';
  assert.ok(page.evidence.includes(quote));
  const candidate={company_name:'New Company',source_url:page.url,evidence_quote:quote,icp_code:'AUTO_1',icp_confidence:.85,icp_reasoning:'Industrial transport services are explicitly documented.',company_identity_verified:true};
  const ws={icp_ids:{AUTO_1:A+'-icp'}};
  assert.equal(discoveryResults(envelope({candidates:[candidate]}),[page],ws,job(),completionContent)[0].candidate.company_name,'New Company');
  assert.equal(discoveryResults(envelope({candidates:[{...candidate,evidence_quote:quote+' We guarantee savings.'}]}),[page],ws,job(),completionContent)[0].failure_reason,'DISCOVERY_EVIDENCE_REJECTED');
});
