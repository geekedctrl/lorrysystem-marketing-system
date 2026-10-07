'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const P=require('./people-runtime');
const R=require('./research-runtime');
const {researchChild}=require('./research-workflows');
const seed={company:{name:'Acme Logistics Sdn Bhd',domain:'acme.com',country_code:'MY'}};
const person={name:'Jane Tan',job_title:'Operations Manager',source_urls:['https://acme.com/team'],linkedin_url:null};
const result=()=>({research_id:'r',lead_id:'l',research_outcome:'COMPLETED',research_payload:{company_facts:{people:[{...person}]}}});
const queries=()=>P.peopleQueries(result(),seed,'MY');
const profile=(url='https://www.linkedin.com/in/jane-tan',title='Jane Tan - Operations Manager - Acme Logistics')=>({url,title,description:'Professional experience and business profile.'});
const response=(...results)=>({statusCode:200,body:{web:{results}}});
const enrich=(responses,evidence={sources:[]})=>P.enrichPeopleProfiles(result(),seed,responses,queries(),evidence);

test('person URLs are canonical; companies, posts, lookalike hosts and unsafe addresses are rejected',()=>{
  assert.equal(P.professionalProfile('https://my.linkedin.com/in/jane-tan/?trk=search').url,'https://www.linkedin.com/in/jane-tan');
  assert.equal(P.professionalProfile('https://twitter.com/janetan').url,'https://x.com/janetan');
  for(const url of ['https://linkedin.com/company/acme','https://linkedin.com/in/jane/posts','https://linkedin.com.evil.com/in/jane',
    'https://github.com/orgs/acme','https://instagram.com/explore','https://x.com/search','http://127.0.0.1/in/jane',
    'https://user:secret@linkedin.com/in/jane','javascript:alert(1)']) assert.equal(P.professionalProfile(url),null,url);
});
test('search is bounded to verified company people and uses country context',()=>{
  const r=result();r.research_payload.company_facts.people=Array.from({length:8},()=>({...person}));
  const q=P.peopleQueries(r,seed,'US');assert.equal(q.length,10);assert.ok(q.every(item=>item.country==='MY'));
  r.research_payload.company_facts.people=[];assert.deepEqual(P.peopleQueries(r,seed,'MY'),[]);
});
test('public LinkedIn name/company match saves canonical profile and original evidence URL',()=>{
  const value=enrich([response(profile()),response()]);
  const p=value.result.research_payload.company_facts.people[0];
  assert.equal(p.profile_search_status,'MATCHED');assert.equal(p.linkedin_url,'https://www.linkedin.com/in/jane-tan');
  assert.equal(p.professional_profiles[0].match_basis,'PUBLIC_NAME_COMPANY_MATCH');
  assert.equal(value.sources.length,1);assert.ok(value.sources[0].evidence.includes('Jane Tan'));
  assert.equal(result().research_payload.company_facts.people[0].linkedin_url,null,'input remains untouched');
});
test('same name elsewhere, partial names and handles without business role are not attributed',()=>{
  const value=enrich([response(profile(undefined,'Jane Tan - Operations Manager - Other Company'),profile(undefined,'Jane Tanner - Acme Logistics')),
    response(profile('https://x.com/jane','Jane Tan - Acme Logistics'))]);
  const p=value.result.research_payload.company_facts.people[0];
  assert.equal(p.profile_search_status,'NOT_FOUND');assert.equal(p.linkedin_url,null);assert.deepEqual(value.sources,[]);
});
test('professional social handle requires name, company and researched role',()=>{
  const value=enrich([response(),response(profile('https://x.com/jane'))]);
  const p=value.result.research_payload.company_facts.people[0];
  assert.equal(p.professional_profiles[0].platform,'X');assert.equal(p.professional_profiles[0].handle,'jane');
});
test('related-person mentions in another profile snippet do not create identity matches',()=>{
  const unrelated=profile('https://linkedin.com/in/sarah','Sarah Shaari - Quanterm Logistics');
  unrelated.description='Jane Tan is Operations Manager at Acme Logistics, mentioned in a post.';
  const p=enrich([response(profile(),unrelated),response()]).result.research_payload.company_facts.people[0];
  assert.equal(p.profile_search_status,'MATCHED');
  assert.equal(p.professional_profiles.length,1);
  assert.equal(p.linkedin_url,'https://www.linkedin.com/in/jane-tan');
});
test('conflicting matches are retained for review without selecting a LinkedIn identity',()=>{
  const value=enrich([response(profile(),profile('https://linkedin.com/in/jane-other')),response()]);
  const p=value.result.research_payload.company_facts.people[0];
  assert.equal(p.profile_search_status,'NEEDS_REVIEW');assert.equal(p.linkedin_url,null);assert.equal(p.profile_candidates.length,2);
});
test('company social footer is ignored; an official link labelled with the person is supported',()=>{
  const evidence={sources:[{url:'https://acme.com/team',official:true,evidence:'Professional profile: Jane Tan https://linkedin.com/in/jane',
    professional_links:[{label:'LinkedIn',url:'https://linkedin.com/in/acme'},{label:'Jane Tan',url:'https://linkedin.com/in/jane'}]}]};
  const p=enrich([response(),response()],evidence).result.research_payload.company_facts.people[0];
  assert.equal(p.professional_profiles.length,1);assert.equal(p.professional_profiles[0].match_basis,'OFFICIAL_NAMED_LINK');
});
test('search outages retain company research and never save raw provider errors',()=>{
  const value=enrich([{statusCode:429,body:{error:'secret'}},{error:{message:'secret'}}]);
  assert.equal(value.result.research_outcome,'COMPLETED');
  assert.equal(value.result.research_payload.company_facts.people[0].profile_search_status,'SEARCH_UNAVAILABLE');
  assert.ok(!JSON.stringify(value).includes('secret'));
  assert.equal(enrich([{statusCode:200,body:{}},response()]).result.research_payload.company_facts.people[0].profile_search_status,'NOT_FOUND');
});
test('known primary contacts get an affiliation query and people snippets retain title evidence',()=>{
  const q=R.researchQueries({...seed,known_contact:{name:'Jane Tan'}},'MY');
  assert.equal(q.length,3);assert.ok(q[2].query.includes('Jane Tan'));
  assert.ok(q[1].query.startsWith('site:acme.com '),'people research prioritizes the official leadership page');
  const sources=R.researchSearchSources([response(profile())],[{purpose:'KNOWN_PERSON'}]);
  assert.ok(sources[0].evidence.includes('Jane Tan'));assert.equal(sources[0].confidence,55);
  assert.equal(sources[0].search_purpose,'KNOWN_PERSON');
  const long=P.peopleQueries(result(),{company:{name:'c'.repeat(200)}},'MY');
  assert.ok(long.every(value=>value.query.length<400));
});
test('bounded page selection reserves official people evidence ahead of general search pages',()=>{
  const searches=Array.from({length:10},(_,i)=>({url:`https://acme.com/service-${i}`,search_purpose:'COMPANY'}));
  searches.push({url:'https://acme.com/leadership',search_purpose:'PEOPLE'});
  const pages=R.selectResearchUrls({...seed,company:{...seed.company,website_url:'https://acme.com/'},sources:[]},searches,6);
  assert.equal(pages.length,6);
  assert.ok(pages.some(page=>page.url==='https://acme.com/leadership'));
});
test('HTML profiles are retained only from official visible named links within evidence budget',()=>{
  const url='https://acme.com/team';
  const html='<p>Jane Tan is Operations Manager at Acme Logistics. Our business provides road haulage across Malaysia.</p>'
    +'<a href="https://linkedin.com/in/jane">Jane Tan</a><script><a href="https://linkedin.com/in/evil">Jane Tan</a></script>';
  const page=R.cleanResearchPage({fetch_status:'SUCCESS',final_url:url,body:html},{url},seed);
  assert.equal(page.professional_links.length,1);assert.ok(page.evidence.includes('Professional profile: Jane Tan'));
  const e=R.assembleResearchEvidence({...seed,sources:[]},[],[page],{max_sources:10,max_evidence_chars:100});
  assert.equal(e.sources[0].professional_links.length,0,'truncated links cannot provide unsaved evidence');
});
test('n8n sandbox has no Node dependency and new graph uses existing Brave and source persistence',()=>{
  const runtime=fs.readFileSync(require.resolve('./research-runtime'),'utf8')+'\n'+fs.readFileSync(require.resolve('./people-runtime'),'utf8');
  const value=vm.runInNewContext(runtime+'\nenrichPeopleProfiles(result,seed,responses,requests,{sources:[]})',
    {module:{exports:{}},result:result(),seed,responses:[response(profile()),response()],requests:queries()});
  assert.equal(value.result.research_payload.company_facts.people[0].profile_search_status,'MATCHED');
  const binding=JSON.parse(fs.readFileSync(require.resolve('./research-binding.example.json'),'utf8'));
  const graph=researchChild(binding);
  assert.deepEqual(graph.nodes.find(n=>n.name==='Search Professional Profiles').credentials.httpHeaderAuth,binding.brave_credential);
  for(const name of ['Search Research Evidence','Search Professional Profiles']) {
    assert.deepEqual(graph.nodes.find(n=>n.name===name).parameters.options.batching,{batch:{batchSize:1,batchInterval:1500}});
  }
  assert.equal(graph.connections['Research Findings Valid?'].main[0][0].node,'People Search Queries');
  assert.equal(graph.connections['Save Profile Source'].main[0][0].node,'Prepare Enriched Research');
});
