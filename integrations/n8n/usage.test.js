'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const {workflowUsage}=require('./usage-runtime');
const node=values=>name=>{if(!(name in values))throw new Error('Not executed');return {all:()=>values[name].map(json=>({json}))};};
test('usage retains only bounded request counts, observed status and reported tokens',()=>{
  const value=workflowUsage(node({'Search Professional Profiles':[{statusCode:200,body:{}},{statusCode:429,body:{error:'SECRET'}}],
    'xKiro Stage Extraction':[{statusCode:200,body:{usage:{prompt_tokens:100,completion_tokens:20},secret:'SECRET'}}]}));
  assert.equal(value.search_requests,2);assert.equal(value.search_status,'ERROR');assert.equal(value.input_tokens,100);
  assert.ok(!JSON.stringify(value).includes('SECRET'));
  assert.equal(workflowUsage(node({'xKiro Stage Extraction':[{}]})).input_tokens,null);
  assert.equal(workflowUsage(node({})).model_status,'NOT_USED');
  const source=fs.readFileSync(require.resolve('./usage-runtime'),'utf8');
  assert.equal(vm.runInNewContext(source+'\nworkflowUsage(node)',{node:node({})}).search_requests,0);
});
test('dispatcher sends usage only when the deployed API supports metrics',()=>{
  const {sharedWorker}=require('./shared-workflows');
  const binding=JSON.parse(fs.readFileSync(require.resolve('./shared-binding.example.json'),'utf8'));
  const code=sharedWorker(binding,{setup:'s',discovery:'d',research:'r',pipeline:'p'}).nodes.find(n=>n.name==='Finish Shared Job Input').parameters.jsCode;
  const job={job_id:'job',lease_token:'lease',input:{}};
  const run=version=>vm.runInNewContext(`(function(){${code}})()`,{$input:{all:()=>[{json:{shared_outcome:'COMPLETED',usage:{search_requests:1}}}]},$:name=>({first:()=>({json:name==='Validate Claimed Job'?job:{body:{automation_metrics_version:version}}})})})[0].json;
  assert.equal(run(undefined).usage,undefined);
  assert.equal(run(1).usage.search_requests,1);
});
