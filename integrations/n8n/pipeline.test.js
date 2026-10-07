'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm');
const R=require('./pipeline-runtime'),{completionContent}=require('./model-runtime');
const {pipelineChild,pipelineWorker}=require('./pipeline-workflows');
const binding={workspace_id:'00000000-0000-0000-0000-000000000001',api_base_url:'http://marketing-api:8000',api_credential:{id:'api',name:'Workspace API'},llm:{base_url:'https://api.xkiro.com/v1',provider:'xkiro',model:'mistralai/mistral-large-2512',max_tokens:6000,credential:{id:'xkiro',name:'xKiro'}}};
const workspace={workspace_id:binding.workspace_id,icp_ids:{FLEET:'icp'},product_ids:{MAIN:'product'}};
const job={id:'run',workspace_id:binding.workspace_id,lead_id:'lead',research_id:'research',contact_id:'contact',stage:'SCORING'};
const quote='Acme operates 40 trucks across Malaysia.',url='https://acme.com/';
const context={run:{...job,status:'RUNNING'},input:{},lead:{id:'lead',company_id:'company',icp_profile_id:'icp'},company:{id:'company'},contact:{id:'contact',company_id:'company'},icp:{id:'icp',qualification_rules:{}},products:[{id:'product',code:'MAIN',description:'Fleet operations software'}],research:{id:'research',lead_id:'lead',research_status:'COMPLETED',summary:quote},rubric:[{criterion:'icp_fit',max_points:100}],sources:[{url,evidence:quote}]};
const citation={source_url:url,evidence_quote:quote};
const scoring={components:[{criterion:'icp_fit',points:80,max_points:100,rationale:'Documented fleet operations.',evidence:[citation]}],rationale:'Public fleet evidence supports this ICP.',gaps:['Buying intent is unknown.']};
const response=output=>({statusCode:200,body:{choices:[{message:{content:JSON.stringify(output)},finish_reason:'stop'}]}});
const validate=(output,stage='SCORING')=>R.validatePipelineOutput(response(output),{...job,stage},context,completionContent);
test('context rejects foreign workspaces, contacts, catalogs and stale research before model work',()=>{
  assert.equal(R.validatePipelineContext(context,job,workspace),context);
  for(const modified of [{...context,run:{...context.run,workspace_id:'foreign'}},{...context,contact:{id:'foreign'}},{...context,products:[{id:'foreign',code:'MAIN'}]},{...context,research:{...context.research,research_status:'RUNNING'}}])assert.throws(()=>R.validatePipelineContext(modified,job,workspace),/context/);
});
test('scores use exact rubric weights and require literal saved evidence for positive points',()=>{
  assert.equal(validate(scoring).pipeline_outcome,'VALID');
  for(const changes of [{points:101},{max_points:90},{criterion:'invented'},{evidence:[]},{evidence:[{...citation,evidence_quote:'Invented public fleet information.'}]},{evidence:[{...citation,source_url:'https://foreign.com/'}]}])assert.equal(validate({...scoring,components:[{...scoring.components[0],...changes}]}).pipeline_outcome,'FAILED');
  assert.equal(validate({...scoring,components:[{...scoring.components[0],points:0,evidence:[]}]}).pipeline_outcome,'VALID');
});
test('score failures identify validation problems without retaining model text',()=>{
  for(const [changes,reason] of [
    [{max_points:90},'INVALID_SCORE_COMPONENT'],
    [{evidence:[]},'INVALID_SCORE_CITATIONS_REQUIRED'],
    [{evidence:null},'INVALID_SCORE_CITATIONS_TYPE'],
    [{evidence:Array.from({length:6},()=>citation)},'INVALID_SCORE_CITATIONS_LIMIT'],
    [{evidence:[{...citation,source_url:'https://foreign.com/'}]},'INVALID_SCORE_SOURCE_URL'],
    [{evidence:[{...citation,evidence_quote:'short'}]},'INVALID_SCORE_QUOTE_LENGTH'],
    [{evidence:[{...citation,evidence_quote:'Unsupported provider response text.'}]},'INVALID_SCORE_QUOTE_MISMATCH'],
  ]) {
    const value=validate({...scoring,components:[{...scoring.components[0],...changes}]});
    assert.equal(value.failure_reason,reason);
    assert.ok(!JSON.stringify(value).includes('Unsupported provider response text'));
    assert.equal(value.output,undefined);
  }
  assert.equal(validate({...scoring,gaps:'invalid'}).failure_reason,'INVALID_SCORE_SCHEMA');
});
test('matching rejects invented and duplicate catalog codes and unsupported fit',()=>{
  const match={product_code:'MAIN',fit_score:80,rationale:'Fleet operations align with the catalog.',evidence:[citation]};
  assert.equal(validate({matches:[match]},'MATCHING').pipeline_outcome,'VALID');
  for(const matches of [[{...match,product_code:'OTHER'}],[match,match],[{...match,evidence:[]}]])assert.equal(validate({matches},'MATCHING').pipeline_outcome,'FAILED');
});
test('matching and drafting report safe citation diagnostics and require contiguous excerpts',()=>{
  const match={product_code:'MAIN',fit_score:80,rationale:'Fleet operations align with the catalog.',evidence:[{...citation,evidence_quote:'Acme operates ... across Malaysia.'}]};
  assert.equal(validate({matches:[match]},'MATCHING').failure_reason,'INVALID_PRODUCT_QUOTE_MISMATCH');
  const draft={subject:'Fleet operations',content:'Your public fleet operations may benefit from a review of our operations software.',evidence:[{...citation,source_url:'https://acme.com/other'}]};
  assert.equal(validate(draft,'DRAFTING').failure_reason,'INVALID_DRAFT_SOURCE_URL');
  assert.equal(validate({...draft,evidence:[{...citation,evidence_quote:'x'.repeat(501)}]},'DRAFTING').failure_reason,'INVALID_DRAFT_QUOTE_LENGTH');
  const request=R.preparePipelineModel(context,workspace,binding.llm,()=> 'Professional').request;
  assert.match(request.messages[0].content,/short contiguous quote verbatim/);
});
test('drafts require bounded professional content with supporting sources; provider errors are sanitized',()=>{
  const draft={subject:'Fleet operations',content:'Your public fleet operations may benefit from a review of our operations software.',evidence:[citation]};
  assert.equal(validate(draft,'DRAFTING').pipeline_outcome,'VALID');
  assert.equal(validate({...draft,evidence:[]},'DRAFTING').pipeline_outcome,'FAILED');
  assert.equal(validate({...draft,content:'x'.repeat(5001)},'DRAFTING').pipeline_outcome,'FAILED');
  for(const provider of [{statusCode:401,body:{error:'SECRET'}},{statusCode:200,body:{choices:[{finish_reason:'length',message:{content:'SECRET'}}]}}]){
    const value=R.validatePipelineOutput(provider,job,context,completionContent);assert.equal(value.pipeline_outcome,'FAILED');assert.ok(!JSON.stringify(value).includes('SECRET'));
  }
});
test('model request keeps workspace context and selected product without sender or approval instructions',()=>{
  const draft={...context,run:{...context.run,stage:'DRAFTING'},input:{channel:'EMAIL',product_id:'product'}};
  const request=R.preparePipelineModel(draft,workspace,binding.llm,()=> 'Professional workspace voice').request;
  assert.equal(JSON.parse(request.messages[1].content).selected_product.id,'product');assert.equal(request.max_tokens,6000);assert.match(request.messages[0].content,/pending human approval/);
});
test('workflow retains n8n credentials, waits for API deployment and uses sandbox-compatible Code nodes',()=>{
  const child=pipelineChild(binding),worker=pipelineWorker(binding,'child');
  assert.deepEqual(child.nodes.find(n=>n.name==='xKiro Stage Extraction').credentials.httpHeaderAuth,binding.llm.credential);
  assert.equal(child.connections['Stage Output Valid?'].main[1][0].node,'Stage Validation Failed');
  assert.equal(child.active,false);assert.equal(worker.active,false);assert.ok(!JSON.stringify(child).includes('api_key'));
  assert.throws(()=>pipelineChild({...binding,llm:{...binding.llm,credential:{...binding.llm.credential,key:'SECRET'}}}),/credential/);
  for(const workflow of [child,worker])for(const node of workflow.nodes.filter(n=>n.type==='n8n-nodes-base.code'))new vm.Script(`(function(){${node.parameters.jsCode}\n})`);
  const wait=worker.nodes.find(n=>n.name==='Wait for Stage API').parameters.jsCode;
  assert.equal(vm.runInNewContext(`(function(){${wait}})()`,{$json:{statusCode:404}})[0].json.worker_status,'WAITING_API_DEPLOYMENT');
  assert.throws(()=>vm.runInNewContext(`(function(){${wait}})()`,{$json:{statusCode:403}}),/rejected/);
  const prepared=child.nodes.find(n=>n.name==='Prepare Stage Model').parameters.jsCode;
  const node=name=>({first:()=>({json:name==='Workspace Guard'?{...job,workspace_context:{...workspace,workspace_name:'Acme',product:{name:'Main'},brand_voice:'Professional',language:'en',country_code:'MY',icps:[context.icp],products:context.products}}:{config:{llm:binding.llm}}})});
  assert.ok(vm.runInNewContext(`(function(){${prepared}})()`,{$json:context,$:node,module:{exports:{}}})[0].json.request);
});
