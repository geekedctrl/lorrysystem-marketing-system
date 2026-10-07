'use strict';

// Only bounded counts/statuses leave this function. Never retain requests, errors or credentials.
function workflowUsage(node) {
  const items=name=>{try{return node(name).all().map(item=>item.json);}catch{return [];}};
  const searches=['Search New Companies','Search Research Evidence','Search Professional Profiles'].flatMap(items);
  const pages=['Fetch New Company Page','Fetch Guarded Research Page','Fetch Official Contact Page'].flatMap(items);
  const models=['xKiro Product Targeting','xKiro Discovery Extraction','xKiro Research Extraction','xKiro Stage Extraction'].flatMap(items);
  const ok=value=>!value.error&&(!value.statusCode||value.statusCode===200)&&!(value.body??value).error;
  const usage=models.map(value=>(value.body??value).usage);
  const reported=models.length>0&&usage.every(value=>value&&['prompt_tokens','completion_tokens'].every(key=>Number.isInteger(value[key])&&value[key]>=0&&value[key]<=1000000));
  return {search_requests:Math.min(searches.length,100),fetch_requests:Math.min(pages.length,100),model_requests:Math.min(models.length,10),
    input_tokens:reported?Math.min(usage.reduce((sum,value)=>sum+value.prompt_tokens,0),1000000):null,
    output_tokens:reported?Math.min(usage.reduce((sum,value)=>sum+value.completion_tokens,0),1000000):null,
    search_status:searches.length?(searches.every(ok)?'OK':'ERROR'):'NOT_USED',
    model_status:models.length?(models.every(ok)?'OK':'ERROR'):'NOT_USED'};
}
if(typeof module!=='undefined')module.exports={workflowUsage};
