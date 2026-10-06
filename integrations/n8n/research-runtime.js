'use strict';

function publicResearchUrl(value) {
  if (typeof value !== 'string' || value.length > 1500 || /[\x00-\x20\x7f]/.test(value)) return null;
  const match=value.match(/^(https?):\/\/([a-z0-9.-]+)(?::(80|443))?([/?#].*)?$/i);
  if (!match || (match[3] && match[3] !== (match[1].toLowerCase()==='https'?'443':'80'))) return null;
  const host=match[2].toLowerCase();
  if (!host.includes('.') || /^\d+(?:\.\d+)*$/.test(host)
      || host.split('.').some(part=>! /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(part))
      || /\.(local|localhost|internal|lan|home|onion|test|invalid|example|arpa)$/.test(host)) return null;
  const suffix=(match[4]||'/').split('#')[0]||'/';
  return {url:`${match[1].toLowerCase()}://${host}${suffix.startsWith('?')?'/':''}${suffix}`,
    host:host.replace(/^www\./,''), key:`${host.replace(/^www\./,'')}${suffix}`};
}

function researchSeed(value, input, context) {
  if (input.workspace_id !== context.workspace_id || !input.research_id
      || value?.research?.id !== input.research_id || value.research.research_status !== 'RUNNING'
      || value.research.lead_id !== input.lead_id || value.lead?.id !== input.lead_id
      || value.company?.id !== value.lead.company_id || value.icp_profile?.id !== value.lead.icp_profile_id
      || !Object.values(context.icp_ids).includes(value.icp_profile.id)) {
    throw new Error('Research seed does not match the claimed workspace job');
  }
  if (value.primary_contact && value.primary_contact.company_id !== value.company.id) {
    throw new Error('Research contact belongs to a different company');
  }
  const candidate=value.accepted_candidate;
  if (candidate && (candidate.status !== 'ACCEPTED' || candidate.accepted_lead_id !== input.lead_id)) {
    throw new Error('Research candidate was not accepted for this lead');
  }
  const sources=[];
  for (const source of (value.candidate_sources||[]).slice(0,6)) {
    if (!candidate || source.candidate_id !== candidate.id) throw new Error('Foreign candidate source');
    const url=publicResearchUrl(source.url);
    const evidence=String(source.evidence||source.summary||'').slice(0,4000);
    if (!url || evidence.length < 40) continue;
    sources.push({url:url.url,source_type:source.source_type==='SEARCH_RESULT'?'SEARCH':'WEBSITE',
      title:String(source.title||'Accepted discovery evidence').slice(0,250),evidence,
      confidence:60,observed_at:source.discovered_at||new Date().toISOString(),origin:'CANDIDATE_EVIDENCE'});
  }
  const website=publicResearchUrl(value.company.website_url)
    || publicResearchUrl(value.company.domain?`https://${value.company.domain}/`:null);
  return {research_id:input.research_id,lead_id:input.lead_id,workspace_id:context.workspace_id,
    company:{name:String(value.company.name).slice(0,200),domain:website?.host||null,
      website_url:website?.url||null,industry:value.company.industry,country_code:value.company.country_code},
    known_contact:value.primary_contact?.full_name?{name:value.primary_contact.full_name,job_title:value.primary_contact.job_title}:null,
    icp:value.icp_profile,sources};
}

function researchQueries(seed, country) {
  const name=seed.company.name.replace(/["\r\n]/g,' ').trim();
  return [
    {query:seed.company.domain?`site:${seed.company.domain} "${name}" about services contact team operations`:`"${name}" company services`,purpose:'COMPANY'},
    {query:`"${name}" managing director operations manager leadership`,purpose:'PEOPLE'},
    ...(seed.known_contact?[{query:`"${String(seed.known_contact.name).replace(/["\r\n]/g,' ')}" "${name}" role company`,purpose:'KNOWN_PERSON'}]:[]),
  ].map(value=>({...value,country:/^[A-Z]{2}$/.test(seed.company.country_code||'')?seed.company.country_code:country}));
}

function researchSearchSources(responses, requests=[]) {
  const values=[];
  for (const [index,response] of responses.entries()) {
    if (response.statusCode && response.statusCode!==200) continue;
    const body=response.body??response;
    for (const result of (body.web?.results||[]).slice(0,10)) {
      const url=publicResearchUrl(result.url);
      const evidence=[result.title,result.description].filter(value=>typeof value==='string').join(' — ').replace(/<[^>]*>/g,' ').trim().slice(0,1500);
      if (!url || evidence.length < 40) continue;
      values.push({url:url.url,source_type:'SEARCH',title:String(result.title||url.host).slice(0,250),
        evidence,confidence:['PEOPLE','KNOWN_PERSON'].includes(requests[index]?.purpose)?55:50,observed_at:new Date().toISOString(),origin:'SEARCH_SNIPPET'});
    }
  }
  return values;
}

function selectResearchUrls(seed, searches, limit) {
  const values=[seed.company.website_url,...seed.sources.map(source=>source.url),...searches.map(source=>source.url)];
  const unique=new Map();
  for (const value of values) {
    const url=publicResearchUrl(value);
    if (!url || /(?:^|\.)(linkedin|facebook|instagram|twitter|youtube|tiktok|x)\.com$/.test(url.host)
        || /\.(pdf|zip|png|jpg|jpeg|svg)(?:$|\?)/i.test(url.url)) continue;
    if (!unique.has(url.key)) unique.set(url.key,{url:url.url,official:url.host===seed.company.domain});
  }
  return [...unique.values()].sort((a,b)=>Number(b.official)-Number(a.official)).slice(0,limit);
}

function decodeResearchText(value) {
  return value.replace(/&nbsp;/gi,' ').replace(/&amp;/gi,'&').replace(/&quot;/gi,'"')
    .replace(/&#39;|&apos;/gi,"'").replace(/&lt;/gi,'<').replace(/&gt;/gi,'>')
    .replace(/&#(x[0-9a-f]+|\d+);/gi,(_,code)=>{
      const n=code[0].toLowerCase()==='x'?parseInt(code.slice(1),16):parseInt(code,10);
      return n>0 && n<=0x10ffff?String.fromCodePoint(n):' ';
    });
}

function cleanResearchPage(response, request, seed) {
  const body=response.body&&typeof response.body==='object'?response.body:response;
  const final=publicResearchUrl(body.final_url||request.url);
  if (response.error || body.fetch_status !== 'SUCCESS' || !final) {
    return {url:request.url,failed:true,failure_reason:body.failure_reason||'FETCH_REQUEST_FAILED'};
  }
  const html=String(body.body||'').slice(0,262144)
    .replace(/<(script|style|noscript|iframe)\b[^>]*>[\s\S]*?<\/\1>/gi,' ')
    .replace(/<!--[\s\S]*?-->/g,' ');
  let text=decodeResearchText(html.replace(/<[^>]*>/g,' ')).replace(/\s+/g,' ').trim();
  const contacts=[], professional_links=[];
  if (final.host===seed.company.domain) {
    for (const match of html.matchAll(/<a\b[^>]*href\s*=\s*["'](https?:\/\/[^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi)) {
      const link=publicResearchUrl(decodeResearchText(match[1]));
      const label=decodeResearchText(match[2].replace(/<[^>]*>/g,' ')).replace(/\s+/g,' ').trim().slice(0,150);
      if (link && /(?:^|\.)(linkedin|instagram|twitter|x|github)\.com$/.test(link.host) && label && professional_links.length<20) {
        professional_links.push({url:link.url,label});
        contacts.push(`Professional profile: ${label} ${link.url}`);
      }
    }
  }
  for (const match of html.matchAll(/href\s*=\s*["'](mailto:|tel:)([^"']+)["']/gi)) {
    const value=decodeResearchText(match[2].split('?')[0]);
    if (value.length<150) contacts.push(`${match[1].toLowerCase()==='mailto:'?'Public business email':'Public business phone'}: ${value}`);
  }
  text=(text+' '+[...new Set(contacts)].join(' ')).trim().slice(0,6000);
  if (text.length<100) return {url:request.url,failed:true,failure_reason:'INSUFFICIENT_PAGE_TEXT'};
  return {url:final.url,source_type:'WEBSITE',title:decodeResearchText((html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)||[])[1]||final.host).trim().slice(0,250),
    evidence:text,confidence:final.host===seed.company.domain?90:65,observed_at:new Date().toISOString(),
    origin:'FETCHED_PAGE',official:final.host===seed.company.domain,professional_links};
}

function assembleResearchEvidence(seed, searches, pages, settings) {
  const unique=new Map();
  // Freshly fetched evidence replaces snippets/previous extraction for a URL.
  for (const source of [...seed.sources,...searches,...pages.filter(page=>!page.failed)]) {
    const url=publicResearchUrl(source.url);
    if (url && source.evidence) unique.set(url.key,{...source,url:url.url});
  }
  const values=[...unique.values()].sort((a,b)=>b.confidence-a.confidence).slice(0,settings.max_sources);
  const perSource=Math.min(4000,Math.floor(settings.max_evidence_chars/Math.max(1,values.length)));
  const sources=values.map(source=>{
    const evidence=source.evidence.slice(0,perSource);
    return {...source,evidence,professional_links:(source.professional_links||[]).filter(link=>evidence.includes(`Professional profile: ${link.label} ${link.url}`))};
  });
  return {...seed,sources,coverage:{pages_fetched:pages.length,official_pages_read:pages.filter(page=>!page.failed&&page.official).length,
    fetch_failures:pages.filter(page=>page.failed).map(page=>({url:page.url,reason:page.failure_reason})),
    search_sources:searches.length,seed_sources:seed.sources.length}};
}

function validateResearchExtraction(response, evidence, llm, completion) {
  const failure=reason=>({research_outcome:'FAILED',failure_reason:reason,research_id:evidence.research_id,lead_id:evidence.lead_id});
  const envelope=completion(response);
  if (envelope.error) return failure(envelope.error);
  let data;
  try { data=JSON.parse(envelope.content.replace(/^```(?:json)?\s*|\s*```$/g,'')); }
  catch (_) { return failure('INVALID_RESEARCH_JSON'); }
  const normalize=value=>String(value||'').toLowerCase().replace(/\s+/g,' ').trim();
  const byUrl=new Map(evidence.sources.map(source=>[source.url,source]));
  const supported=(record)=>Array.isArray(record.source_urls) && record.source_urls.length>0 && record.source_urls.length<=5
    && record.source_urls.every(url=>byUrl.has(url))
    && typeof record.evidence_quote==='string' && record.evidence_quote.trim().length>=8 && record.evidence_quote.length<=500
    && record.source_urls.some(url=>normalize(byUrl.get(url).evidence).includes(normalize(record.evidence_quote)));
  const confidence=value=>Number.isInteger(value)&&value>=0&&value<=100;
  if (!data || typeof data.company_summary !== 'string' || data.company_summary.trim().length<20
      || data.company_summary.length>2000 || typeof data.company_identity_verified !== 'boolean' || !confidence(data.confidence)
      || !Array.isArray(data.facts) || data.facts.length>25 || !Array.isArray(data.people) || data.people.length>5
      || !Array.isArray(data.summary_sources) || !data.summary_sources.length
      || data.summary_sources.some(url=>!byUrl.has(url))) return failure('INVALID_RESEARCH_SCHEMA');
  const categories=['COMPANY','SERVICES','FLEET','TECHNOLOGY','LOCATION','SIGNAL','PAIN_POINT'];
  const facts=data.facts.filter(fact=>fact&&categories.includes(fact.category)&&typeof fact.fact==='string'
    && fact.fact.length>=8&&fact.fact.length<=600&&confidence(fact.confidence)&&supported(fact)
    && (fact.evidence_status==='OBSERVED'||(fact.category==='PAIN_POINT'&&fact.evidence_status==='INFERRED')))
    .map(fact=>({category:fact.category,...(typeof fact.title==='string'&&fact.title.trim().length>=3&&fact.title.trim().length<=80?{title:fact.title.trim()}:{}),fact:fact.fact,evidence_status:fact.evidence_status,
      evidence_quote:fact.evidence_quote,source_urls:fact.source_urls,confidence:fact.confidence}));
  const people=[];
  for (const person of data.people) {
    if (!person || typeof person.name!=='string' || person.name.length<3||person.name.length>120
        || typeof person.job_title!=='string'||person.job_title.length>150||!confidence(person.confidence)||!supported(person)
        || !['EXECUTIVE','DECISION_MAKER','INFLUENCER','OPERATIONAL_CONTACT'].includes(person.role_classification)) continue;
    const texts=person.source_urls.map(url=>byUrl.get(url).evidence);
    if (!texts.some(text=>normalize(text).includes(normalize(person.name)))) continue;
    if (person.job_title && !texts.some(text=>normalize(text).includes(normalize(person.job_title)))) continue;
    if (!normalize(person.evidence_quote).includes(normalize(person.name))
        || (person.job_title && !normalize(person.evidence_quote).includes(normalize(person.job_title)))) continue;
    // External people evidence must explicitly tie the person to the company.
    const companyName=normalize(normalize(evidence.company.name).replace(/\b(sdn|bhd|berhad|limited|ltd|inc)\b\.?/g,''));
    const associated=person.source_urls.some(url=>publicResearchUrl(url).host===evidence.company.domain)
      || (companyName.length>=3 && texts.some(text=>normalize(text).includes(companyName)));
    if (!associated) continue;
    const email=typeof person.business_email==='string'&&/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(person.business_email)
      && normalize(person.evidence_quote).includes(normalize(person.business_email))?person.business_email:null;
    const phone=typeof person.business_phone==='string'&&person.business_phone.length<=60
      && person.business_phone.replace(/\D/g,'').length>=7
      && person.evidence_quote.replace(/\D/g,'').includes(person.business_phone.replace(/\D/g,''))?person.business_phone:null;
    const profile=publicResearchUrl(person.linkedin_url);
    const linkedin=profile&&profile.host==='linkedin.com'&&/\/in\/[^/?]+/.test(profile.url)
      && texts.some(text=>text.includes(person.linkedin_url))?profile.url:null;
    people.push({name:person.name,job_title:person.job_title,role_classification:person.role_classification,
      business_email:email,business_phone:phone,linkedin_url:linkedin,source_urls:person.source_urls,
      evidence_quote:person.evidence_quote,confidence:person.confidence});
  }
  if (!facts.length) return failure('NO_SUPPORTED_RESEARCH_FACTS');
  const complete=data.company_identity_verified===true&&evidence.coverage.official_pages_read>0
    && facts.some(fact=>fact.category==='SERVICES'&&fact.evidence_status==='OBSERVED')&&data.confidence>=70;
  const classification=data.industry_classification;
  const industry=classification && typeof classification.label==='string' && classification.label.trim().length>=3
    && classification.label.trim().length<=120 && !/[\x00-\x1f<>]/.test(classification.label)
    && confidence(classification.confidence) && classification.confidence>=75 && supported(classification)
    && classification.source_urls.some(url=>byUrl.get(url).official===true
      && normalize(byUrl.get(url).evidence).includes(normalize(classification.evidence_quote)))
    ? {label:classification.label.trim(),confidence:classification.confidence,evidence_quote:classification.evidence_quote,
      source_urls:classification.source_urls} : null;
  const report={summary:data.company_summary.trim(),confidence:complete?data.confidence:Math.min(data.confidence,65),
    pain_points:facts.filter(fact=>fact.category==='PAIN_POINT').map(fact=>`${fact.evidence_status==='INFERRED'?'Possible: ':''}${fact.fact}`),
    buying_signals:facts.filter(fact=>fact.category==='SIGNAL').map(fact=>fact.fact),
    company_facts:{research_version:'workspace-research-v1',facts,people,industry_classification:industry,coverage:evidence.coverage,
      company_identity_verified:complete,missing_information:Array.isArray(data.missing_information)?data.missing_information.filter(x=>typeof x==='string'&&x.length<=300).slice(0,12):[],
      model_usage:envelope.usage},model_provider:llm.provider,model_name:llm.model,raw_output:null};
  return {research_id:evidence.research_id,lead_id:evidence.lead_id,research_outcome:complete?'COMPLETED':'PARTIAL',
    finish_endpoint:complete?'complete':'partial',research_payload:report};
}

if (typeof module !== 'undefined') module.exports={publicResearchUrl,researchSeed,researchQueries,researchSearchSources,
  selectResearchUrls,cleanResearchPage,assembleResearchEvidence,validateResearchExtraction};
