'use strict';

// Uses publicResearchUrl from research-runtime in the n8n Code sandbox.
function professionalProfile(value) {
  const parsed=publicResearchUrl(value);
  if (!parsed) return null;
  const path=parsed.url.replace(/^https?:\/\/[^/]+/,'').split('?')[0].replace(/\/$/,'');
  let platform, handle;
  if (/^(?:[a-z]{2}\.)?linkedin\.com$/.test(parsed.host) && /^\/in\/[a-z0-9_%.-]+$/i.test(path)) {
    platform='LinkedIn'; handle=path.slice(4);
  } else if (['x.com','twitter.com','instagram.com','github.com'].includes(parsed.host)
      && /^\/[a-z0-9_.-]{1,50}$/i.test(path)
      && !/^\/(home|search|explore|intent|share|login|signup|settings|about|company|orgs|topics|reels|p)$/i.test(path)) {
    platform={'x.com':'X','twitter.com':'X','instagram.com':'Instagram','github.com':'GitHub'}[parsed.host];
    handle=path.slice(1);
  } else return null;
  return {platform,handle,url:`https://${platform==='LinkedIn'?'www.linkedin.com':platform==='X'?'x.com':parsed.host}${path}`};
}

function peopleText(value) {
  return String(value||'').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu,' ').trim();
}
function peopleContains(text, value) {
  const phrase=peopleText(value);
  return phrase.length>=3 && (` ${peopleText(text)} `).includes(` ${phrase} `);
}
function peopleCompany(value) {
  return peopleText(value).replace(/\b(sdn|bhd|berhad|limited|ltd|inc|llc|corp|corporation)\b/g,'').replace(/\s+/g,' ').trim();
}

function peopleQueries(result, seed, country) {
  const people=result.research_payload.company_facts.people.slice(0,5);
  const clean=value=>String(value).replace(/["\r\n]/g,' ').trim().slice(0,100);
  return people.flatMap((person,index)=>[
    {person_index:index,query:`"${clean(person.name)}" "${clean(seed.company.name)}" site:linkedin.com/in/`,purpose:'LINKEDIN'},
    {person_index:index,query:`"${clean(person.name)}" "${clean(seed.company.name)}" (site:x.com OR site:twitter.com OR site:instagram.com OR site:github.com)`,purpose:'PROFESSIONAL_SOCIAL'},
  ]).map(item=>({...item,country:/^[A-Z]{2}$/.test(seed.company.country_code||'')?seed.company.country_code:country}));
}

function enrichPeopleProfiles(result, seed, responses, requests, evidence) {
  // Affiliation is established by company research before any named-person search.
  const output=JSON.parse(JSON.stringify(result));
  const people=output.research_payload.company_facts.people;
  const saved=new Map();
  let unavailable=0;
  people.forEach((person,index)=>{
    const candidates=new Map();
    const add=(profile,source,quote,basis)=>{
      if (!profile) return;
      if (!candidates.has(profile.url)) candidates.set(profile.url,{...profile,match_basis:basis,
        evidence_quote:quote,source_urls:[source.url],confidence:basis==='OFFICIAL_NAMED_LINK'?90:75});
      saved.set(source.url,source);
    };
    // An official page must label the outgoing profile link with this person's name.
    for (const source of evidence.sources) {
      if (!source.official) continue;
      for (const link of source.professional_links||[]) {
        if (peopleContains(link.label,person.name)) add(professionalProfile(link.url),source,
          `Professional profile: ${link.label} ${link.url}`,'OFFICIAL_NAMED_LINK');
      }
    }
    const own=responses.filter((_,i)=>requests[i]?.person_index===index);
    let failed=0;
    for (const response of own) {
      const body=response.body??response;
      if (response.error || (response.statusCode && response.statusCode!==200) || !body || typeof body!=='object' || body.error) {
        failed++; continue;
      }
      for (const item of (Array.isArray(body.web?.results)?body.web.results:[]).slice(0,5)) {
        const profile=professionalProfile(item.url);
        if (!profile) continue;
        const quote=[item.title,item.description].filter(x=>typeof x==='string').join(' — ').replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim().slice(0,1800);
        if (!peopleContains(item.title,person.name) || !peopleContains(quote,peopleCompany(seed.company.name))) continue;
        // A social handle also needs the researched business role, not just the same name.
        if (profile.platform!=='LinkedIn' && (!person.job_title || !peopleContains(quote,person.job_title))) continue;
        const source={url:item.url,source_type:'SEARCH',title:String(item.title||profile.platform).slice(0,250),
          evidence:quote,confidence:75,observed_at:new Date().toISOString()};
        add(profile,source,quote,'PUBLIC_NAME_COMPANY_MATCH');
      }
    }
    unavailable+=failed;
    const values=[...candidates.values()];
    const platforms=[...new Set(values.map(value=>value.platform))];
    person.professional_profiles=[]; person.profile_candidates=[];
    for (const platform of platforms) {
      const group=values.filter(value=>value.platform===platform);
      // Conflicting profiles are retained for review, never picked by model confidence.
      if (group.length===1) person.professional_profiles.push({...group[0],match_status:'MATCHED'});
      else person.profile_candidates.push(...group.map(value=>({...value,match_status:'NEEDS_REVIEW'})));
    }
    person.linkedin_url=person.professional_profiles.find(value=>value.platform==='LinkedIn')?.url||null;
    person.profile_search_status=person.profile_candidates.length?'NEEDS_REVIEW':person.professional_profiles.length?'MATCHED':failed?'SEARCH_UNAVAILABLE':'NOT_FOUND';
  });
  output.research_payload.company_facts.people_search={version:'public-professional-v1',searched_people:people.length,
    search_queries:requests.length,unavailable_queries:unavailable,completed_at:new Date().toISOString()};
  return {result:output,sources:[...saved.values()]};
}

if (typeof module !== 'undefined') {
  var publicResearchUrl;
  if (typeof publicResearchUrl !== 'function') publicResearchUrl=require('./research-runtime').publicResearchUrl;
  module.exports={professionalProfile,peopleQueries,enrichPeopleProfiles};
}
