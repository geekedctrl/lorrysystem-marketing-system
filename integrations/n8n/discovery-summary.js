// One summary after every terminal branch (including empty and skipped results).
function items(name) {
  try { return $(name).all().map(item => item.json); } catch (_) { return []; }
}
const outcomes = items('Normalize Candidate API Outcome');
const fetches = items('Classify Fetch Result');
const extraction = items('Validate AI Extraction');
const apiFailed = outcomes.some(item => !item.candidate_api_ok);
const summary = {
  search_results:items('Brave Search').reduce((count,item)=>count+(item.web?.results?.length||0),0),
  websites_fetched:fetches.length,
  existing_skipped:items('Registry Skip Result').length,
  new_candidates:outcomes.filter(item=>['NEW_CANDIDATE','EXISTING_COMPANY'].includes(item.candidate_outcome)).length,
  existing_candidates:outcomes.filter(item=>item.candidate_outcome === 'EXISTING_CANDIDATE').length,
  fetch_failures:fetches.filter(item=>item.fetch_status !== 'SUCCESS').length,
  model_failures:extraction.filter(item=>item.ai_extraction_status !== 'VALID').length,
};
return [{json:{discovery_summary:true,status:apiFailed?'FAILED':'COMPLETED',
  error_code:apiFailed?'CANDIDATE_API_FAILED':null,summary}}];
