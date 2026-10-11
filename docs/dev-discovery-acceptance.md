# DEV discovery acceptance — 11 October 2026

The user requested a real discovery test against `dashboard-dev.obsidian.cam` because new companies were not appearing. The deployed checkout was `75d7d9e` (frontend PR #31). Running services still use `dashboard.app.main` / the legacy marketing API and n8n queue. No independent native API or native worker service was running. Having the rebuild source in Git does not switch the deployed executor.

## Connection and scope

The public dashboard returned HTTP 403 to this machine's HTTP client; no connected GUI browser was available. The existing authorized SSH jump chain reached DietPi. A temporary loopback-only SSH forward reached the actual DEV dashboard on server localhost8081. Tests used normal dashboard login, workspace selection, CSRF-protected Find Lead submission, status polling and rendered lead pages. This verifies the deployed application behind its ingress; it does not establish that a public browser session passes the ingress checks.

All batches targeted one new company in LorrySystem, using the real Brave and existing named xKiro credentials. No fake companies were inserted. Automatic preparation remained enabled; no approval or sending action was performed. No Compose deployment, account migration or executor cutover occurred.

## Findings and fixes

The original test completed with `NO_NEW_SUITABLE_COMPANIES`. A temporarily retained child execution showed 20 Brave results, two fetched official company pages, and two model candidates. Evidence validation correctly rejected both: Yoong Mei's model name used `&` while its exact source quote used `and`; Soon Lee's quote used a visible apostrophe where cleaned source text still contained `&rsquo;`. Empty validated results were misleadingly reported as successful no-match discovery.

Changes in the DEV Shared Company Discovery child and repository generator:

- Decode common visible HTML punctuation before providing and saving page evidence. Exact contiguous quotation validation remains enforced; fabricated claims still fail.
- Publish the current extraction instructions requiring the company name from the quote and an unchanged continuous source substring.
- Return `DISCOVERY_EVIDENCE_REJECTED` when the model proposes candidates but none pass validation. A genuine empty candidate array remains a completed no-match result.
- Use literal upstream node references when collecting n8n task-runner usage. Previously the dynamic references silently returned zero for every count; the patched real execution reports its search, fetch and model calls and model token usage.

Only six Code node bodies in the DEV discovery child were updated. Existing graph connections, named credentials and workspace/lease protections were retained. Other live child workflows were not patched. Temporary execution-saving settings were restored to `none` for success and error after verification; diagnostic executions already saved remain available in n8n history. Those raw exports/cookies are private ignored local files, not repository artifacts.

## Verified result

Query: `Malaysia Johor trucking transport haulage company official website`, target1.

| Evidence | Result |
| --- | --- |
| Discovery job | `90c1b0da-3bbc-4b06-bf3c-fb509bb03796`, COMPLETED, one accepted lead |
| n8n execution | `20782`, success |
| Real company | Soon Lee Transport Sdn Bhd, `lorrytransport.com.my` |
| Lead | `3e82bbe4-0a0d-4834-9b52-21e167e1d573` |
| Provider observations | 1 search, 2 public-page fetches, 1 model request; 3511 input and 479 output tokens |
| Dashboard reads | Leads list and lead detail HTTP200, company present; Discovered Leads → All also contains it |
| Research handoff | Research `bad19533-ae96-45d4-8f14-0a4ca7a6444a` ran automatically and completed; verified identity, six findings and two people saved |
| Preparation stop | Research automation job reached NEEDS_REVIEW / SUPPORTED_CONTACT_REQUIRED; no supported outreach contact was selected automatically |

The default Discovered Leads filter shows reviewable candidates. Activated product automation immediately accepts suitable companies, so they appear in Leads and in Discovered Leads → All, rather than the default reviewable list. This filtering is independent of provider execution.

Regression verification: all 73 `integrations/n8n/*.test.js` tests passed, including strict rejection, genuine no-match, visible HTML punctuation and generated usage collection. This is one successful real discovery calibration, not evidence of reliable coverage across every company or product. Provider usage is observed; billing/cost reconciliation remains separate. Native backend integration is still a separate runtime rollout.
