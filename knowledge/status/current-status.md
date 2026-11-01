# Current implementation and next work

Updated: 14 October 2026. The native DEV dashboard/API and Python worker are running without n8n orchestration. The PR #43 research-output recovery fix is merged and present in DEV. The worker image was initially stale because the DietPi deployment helper did not rebuild native services; that persistent helper now builds and starts the native API, worker and dashboard, runs both migrations, backs up both databases, and verifies native health and migration state. Its Bash syntax and read-only develop preflight pass. Retry the failed research run and complete research-through-approval acceptance next; keep legacy/n8n and production available until that acceptance passes.

Latest local follow-up: native discovery now qualifies prospect type separately from ICP relevance and excludes software vendors/consultants, with operator-focused queries and an Optibus-like regression. This change is not yet released; older candidate records remain unchanged until reassessed after release.

14 October scoring follow-up: the ITS Logistics native preparation run completed research and contact search, then failed scoring on response shape. After PR #44 deployed, a controlled retry confirmed criteria now arrive in the expected array, but xKiro used `quote` instead of `evidence_quote` in citations. PR #45 adds a bounded alias normalizer and stricter schema guidance; both response variations have synthetic full-pipeline regressions to pending approval. PR #45 targets `develop`; CI, merge and deployment are pending. The failed run is currently FAILED after the retry; retry it again after the updated build deploys. One additional provider scoring request was made during the retry; no outreach was sent.

## Native worker research failure — 13 October 2026

User verified the public native DEV dashboard and accepted a discovery candidate. The accepted company created a research run, but only the RESEARCH job ran; it failed with `MODEL_OUTPUT_INVALID`, so contact search, scoring, matching and drafting were never queued. Provider ledger showed a successful xKiro response (9,436 tokens), ruling out a connection/authentication failure. Read-only inspection of that response found 21 facts and more than five named people. The managed research contract permits at most five people; after capping to five, the remaining schema validated, with one fact's quote unsupported by fetched pages. The single unsupported fact should be omitted while valid findings continue. Root cause: research validation treated bounded-output overflow and one bad citation as a fatal whole-stage failure, and the prompt did not state the five-person limit.

The merged implementation instructs xKiro to return at most five people, deterministically caps extra contacts before schema validation, drops individual unsupported facts/contacts, records an omission note in research unknowns, and reports generic stage schema problems as `MODEL_OUTPUT_SCHEMA_INVALID`. A PostgreSQL-backed regression exercises an overlong contacts response and unsupported quote while verifying that valid research is saved and CONTACT_SEARCH is queued. Full backend suite: 54 tests passed, one optional Chromium test skipped. PR #43 is merged and deployed; the failed runs have not yet been retried. Do not mark research/contact/scoring/drafting live acceptance complete until a real DEV run reaches human approval.

## Native DEV rollout status — 12 October 2026

PR #38 (`geekedctrl/native-dev-cutover`) deployed the native Python API, durable worker and separate PostgreSQL database alongside the legacy app. Follow-up PR [#39](https://github.com/geekedctrl/lorrysystem-marketing-system/pull/39), based on `develop`, switches `dashboard-dev` to the native UI on loopback port 8081 and retains the former UI on 8082. The native UI talks directly to the native API. CI routes old UI regressions through the legacy service while checking the native UI/API. An additive catalog restore command adds all nine documented LorrySystem solution lines and seven proposed ICPs, preserving the existing AI_DASHCAM, GPS, MDVR and TMS codes. Provider env wiring targets Brave and xKiro (`mistralai/mistral-large-2512`); keys and verified rates must be set privately on DietPi. Local disposable startup/network checks passed; all 51 backend tests and 10 native BFF tests passed with the full nine-product seed. All PR checks passed; merge remains the user's action. No paid provider calls were made.

The native dashboard binds to 8081 and is available through the existing DEV route. The current native workspace/catalog and provider setup remain separate from the legacy database. The persistent DietPi helper now rebuilds and verifies native services on each future deployment. Existing accounts/catalog/leads/approvals/credentials in legacy DB remain separate. The native dashboard session store is process-local and intended for one DEV instance only. See [native dashboard setup](../../docs/native-dashboard-dev.md) and [native DEV cutover](../../docs/native-dev-cutover.md).

| Area | Current state |
| --- | --- |
| Multi-product access | Private workspaces, separate teams, catalogs, ICPs, discovery memory and credentials implemented. Brought forward from original MVP3. |
| Product onboarding | Admin catalog forms activate shared workspace-aware automation; product teams do not configure n8n templates. |
| Dashboard | Deployed FastAPI/Jinja2 dashboard with responsive navigation, company/contact overview and sourced research brief. |
| Discovery | Active DEV shared workflow; two fresh targeted batches have each accepted one new company. Earlier broad batches found none. Batch limits are maxima, not promised lead counts. |
| Research and people | Evidence-based company/industry research and supported professional-profile search implemented. New bounded official leadership/contact-page follow-up is active in DEV and being validated. |
| Preparation | Contact review, scoring, qualification, matching and draft preparation stop at pending human approval. Earlier real Quanterm test reached approval after fixes/retries. Missing reachable contacts stop for review rather than fabricated identities. |
| Status/operations | PR #23 deployed: current-attempt warnings, retained history, worker heartbeat, stalled-job alerts, observed provider outcomes and usage/optional cost estimates. |
| Sending | PR #23 deployed: per-workspace encrypted SMTP accounts, separate human send action, immutable approval checks, suppressions and duplicate prevention. No LorrySystem sender account observed; real configuration/delivery test pending. |
| Database | Deployed release includes migrations through 014: automation observability and controlled SMTP sending. |
| Validation | 183 workspace checks, pipeline/shared automation and migration regressions, synthetic two-product preparation, simulated SMTP and desktop/mobile tests passed. Latest contact-coverage change passes 70 n8n tests. These do not substitute for live acceptance. |

## MVP1 acceptance work

1. Validate several real companies with consistent discovery/research/preparation and sensible review stops. Current contact-coverage fix follows official management/board links within the existing total page budget; Kontena Nasional now has four named contacts saved, but no supported reachable profile/email.
2. Review real scoring, matches and drafts for documented need versus capability relevance, unsupported promises and repetition.
3. Configure AIPath's actual catalog/profile and test the same shared workflows against the unrelated product. User authorized a fictitious Invoice Assist catalog, entered through the admin form. Shared targeting/discovery/research reached contact review for 3E Accounting; temporary product paused after testing.
4. The user confirms the server encryption key is configured. Configure a verified workspace sender later; SMTP testing is explicitly deferred. Ask the user for an explicitly authorized controlled recipient, review/approve a test draft separately, then confirm SMTP acceptance and receipt. Do not send real prospect outreach during acceptance tests.

See [MVP1 acceptance](../automation/mvp1-acceptance.md), [reliability and SMTP](../automation/preparation-reliability-and-sending.md), [company research](../automation/company-research.md) and [the roadmap](../product/product-workspaces-roadmap.md).

MVP2 expansion, broader social discovery, difficult-site browser fallback, campaign coordination and mature analytics are deferred while MVP1 acceptance is incomplete.

Latest calibration: Quanterm 25/100 with unmet need and buying signals zero absent cited observed facts. New generated-draft context guards prevent approving/sending stale research, score, contact or catalog results after the next PR deployment. Current new companies stop for supported contact review. Real fresh matching/draft quality remains outstanding; do not claim complete MVP1 acceptance.

8 October: implemented lead-page contact resolution and Continue preparation for admins/operators. API, two-product fixtures and desktop/mobile checks pass locally; release included in PR #24 update. Real draft acceptance and deferred SMTP remain outstanding.

Deployment confirmation (8October2026): CD succeeded for develop0e51dd3, APIhealthy200/dashboard302, migration014. Contact-resolution and preparation safeguards are deployed in this release; prior pending-deployment notes above are superseded. SMTP delivery remains deferred.

11 October2026: user requested a rebuild and confirmed backend/workers first. New backend/ uses native Python workers and an independent local database. Foundation tests (ten PostgreSQL integration checks plus restricted-role runtime smoke) pass. Discovery/deeper research and downstream stages are next. No existing data/accounts/providers or deployment have been migrated. Docker internal health works; Windows host forwarding remains unresolved.

11 October next implementation: native worker pipeline contracts/provider foundation, then workspace-level product setup/discovery and lead preparation stages. See architecture/native-worker-migration-plan.md. n8n remains required by current deployed system until tested cutover.

11 October implementation: native shared setup, discovery, deeper research, contact search, scoring, matching and drafting are implemented locally. Eligible leads stop at pending human approval. Thirty PostgreSQL integration tests include six synthetic companies across two unrelated catalogs; live provider quality and sending remain unverified. Existing dashboard/data/provider migration and executor cutover remain outstanding; n8n has not been disabled.

11 October publication: native preparation workers and portable frontend handoff pushed at 275ccfb; PR #29 is open against develop (https://github.com/geekedctrl/lorrysystem-marketing-system/pull/29). Remote CI pending at publication. Replacement runtime still requires dashboard/provider/data/sending migration and controlled cutover; existing deployed n8n remains active.

11 October: BE-01–BE-06 native frontend backend support implemented locally on rebuild/native-frontend-support (based on merged PR #29). Typed capabilities/responses, detail/paging, immutable human revisions/separate reviewer, catalog soft lifecycle/versioning and safe partial setup retries. Actual worker idle scheduling fixed. 37 PostgreSQL tests, real API/BFF/DB/worker two-product and restricted API revision/lifecycle acceptance, headless Edge form/preparation/approval/role/tablet/mobile and no-provider rebuild smoke pass. Independent native-acceptance Compose; tested localhost8095 fallback for broken Windows Docker forwarding. See docs/native-frontend-backend-support.md and architecture/native-frontend-backend-support.md. Frontend owner adapters/count-render fix remain separate. No live spend/send/deploy/cutover; no frontend-owned file changes. New code local, not pushed/deployed.

Native frontend backend support is committed locally at fd6c5a3 on rebuild/native-frontend-support; 37 database tests and actual two-product browser/API/worker acceptance passed. Frontend adapters and deployment/cutover remain outstanding.

Native frontend support fd6c5a3 is now pushed to origin/rebuild/native-frontend-support. Merge/deployment pending; target branch develop.

11 October: user-authorized real DEV dashboard discovery verified via SSH loopback. Patched existing Shared Company Discovery for HTML punctuation decoding, visible DISCOVERY_EVIDENCE_REJECTED and real usage counts. Job90c1b0da-3bbc-4b06-bf3c-fb509bb03796 accepted Soon Lee Transport Sdn Bhd, visible in Leads and Discovered Leads All. Research queued. 73 JS tests pass. No sending/app deployment/native cutover. See docs/dev-discovery-acceptance.md.

Follow-up: Soon Lee automatic research completed with verified company identity, six findings and two people. Preparation stopped at NEEDS_REVIEW / SUPPORTED_CONTACT_REQUIRED, preserving the contact review gate.

DEV discovery fixes checkpointed locally as 2f3cba2 on fix/dev-discovery-evidence; not yet pushed. Six discovery Code nodes are already corrected in DEV n8n. Temporary trace retention restored to none; own test session logged out.

11 October 2026 DEV deployment confirmed: discovery fix was rebased onto current develop (including frontend PR #31), pushed as a323efb43e0bc84c6c6ca64c3fdb6b0529b59e73 on fix/dev-discovery-evidence. PR #32 targets develop and remains open for the user to merge. Both push and PR GitHub CI passed. Manual DEV workflow run38140949309 succeeded; deployment record and server HEAD match a323efb, deployed at2026-10-11T12:53:09Z by lorryrunner. API/dashboard health HTTP200; real Soon Lee lead and completed research retained; six published discovery Code fixes still match and retention remains none. No production deployment or native-executor cutover. User local .gitignore/docker-compose edits preserved byte-for-byte and excluded from push.
PR: https://github.com/geekedctrl/lorrysystem-marketing-system/pull/32
Deployment: https://github.com/geekedctrl/lorrysystem-deploy/actions/runs/38140949309

## DEV login recovery — 11 October 2026

Current work: fix/login-session-recovery, based on develop8c62de7 (user merged/deployed PR32). Stale login POSTs previously returned a bare403 and reloading repeated the invalid submission. Login now redirects303 to a fresh GET form; invalid/missing CSRF cannot reach the account API. A dedicated host-only marketing_dashboard_session cookie prevents generic-session conflicts; existing users sign in once. Initial browser mismatch cause remains unconfirmed. Public DEV GETs returned stable fresh tokens, no-store and Cloudflare DYNAMIC. See ../dashboard-login-recovery.md.

Local acceptance: ten synthetic HTTP session/login regressions, eight campaign dashboard, eight research presentation and five UX tests pass. CI includes the new login suite. User-owned .gitignore/docker-compose.yml edits are preserved. DEV deployment is authorized by the user's existing request; production and outbound sending remain outside scope. Remote CI/deployment acceptance is pending.

### DEV release acceptance — 11 October 2026, 13:23 UTC

DONE: login fix d740ed04080ae2cfb5e6900c4fe5beef7057adae deployed to DEV through successful deployment run38142917502 (https://github.com/geekedctrl/lorrysystem-deploy/actions/runs/38142917502). Both code CI runs passed: push38142704887 and PR38142725972. Public HTTPS verification passed for the dedicated cookie, invalid-token recovery to GET, actual admin sign-in/dashboard rendering and logout of the test-owned session. Cookie/password values were not logged; the temporary private verification script was deleted. Initial browser mismatch remains unconfirmed, but the reload trap is reproduced and corrected.

PR33 targets develop: https://github.com/geekedctrl/lorrysystem-marketing-system/pull/33. It remains open for the user's merge; deployment already contains the code fix. This completion record is a documentation-only follow-up. Production, accounts/passwords/keys, n8n and outbound sending were unchanged. User-owned local compose/gitignore hashes match their original values. Users should open https://dashboard-dev.obsidian.cam/login directly and sign in with the fresh form; the new cookie requires one sign-in.

## Recurring DEV session mismatch — 11 October 2026

User still sees /login?notice=session-expired on the repaired DEV runtime. Reproduced a concurrent session overwrite: hold a static response until after login and new-form generation; Starlette's unchanged-session Set-Cookie restores the old anonymous cookie and rejects the new token. Sequential verification had missed this. StableSessionMiddleware now suppresses only unchanged dashboard cookie writes, retaining signed mutation/expiry/logout behavior. Missing cookies have an actionable message; logs record only rejection reason categories. Whether this race caused the user's browser request is not yet confirmed.

Local acceptance:13 login/session HTTP tests (including a regression that failed before the fix, delayed static response, expiry, read-only cookie suppression and security gates),8 campaign dashboard,8 research and5 UX pass. See ../dashboard-login-recovery.md. Existing PR33 against develop will be updated; CI and DEV re-verification pending. User-owned local files preserved. Native frontend and production remain unchanged.

### Stable-session DEV acceptance — 11 October 2026

Code678c5d10ffb06f72458e280ca649d99feebe2a5a passed both complete CI runs38143665891 (push) and38143669343 (PR). DEV deployment38143843825 succeeded: https://github.com/geekedctrl/lorrysystem-deploy/actions/runs/38143843825. Public HTTPS checks passed: no cookie rewrite on unchanged login/static/health/dashboard, stale-token recovery, specific missing-cookie explanation, actual admin sign-in/session retention and test-session logout. All13 controlled HTTP tests also passed against the deployed image, including the delayed-response regression. The temporary private verifier was deleted.

The user has been asked to retry their affected browser. Exact browser-specific root cause remains unconfirmed until that result; the reproduced cookie-overwrite race is corrected and rejection logs now distinguish missing, invalid/expired and mismatched session state without logging sensitive values. PR33 remains open with base develop. No production, provider, outbound-send, account/password/key or user-owned compose/gitignore changes.

## DEV company discovery selection — 11 October 2026

Current branch fix/company-discovery-selection includes the unmerged PR33 session repair to preserve the running DEV baseline. Recent default-query jobs completed with zero companies despite healthy worker/provider activity. A bounded search probe confirmed directory/ranking starvation before a new official company homepage. Shared search now adds official-company wording and safe workspace-memory site exclusions; directories are removed before fetch budgeting and homepages rank first. All-fetch failures are explicit, and managed dashboard polling shows accepted results in All discoveries. Product setup targets observable customer business types. See ../company-discovery-selection.md.

Local acceptance:76 n8n tests,13 login/session checks,8 campaign dashboard and5 UX pass; discovery JS syntax passes. Refined search returns official operator sites. CI, live workflow publication, DEV app release and dashboard batch acceptance pending. User-owned gitignore/compose preserved; production and sending outside scope. New PR base develop; PR33 may be merged first to remove overlapping session changes.

### Exact discovery excerpts — 11 October 2026

Initial corrected default-query batches a1a4bdf0 and ca5f5ec8 reached official KGW/Hock Cheong pages but failed DISCOVERY_EVIDENCE_REJECTED. Diagnostic execution21159 confirmed that the model stitched nonadjacent Hock Cheong passages into one quote. Temporarily enabled child execution saving was restored to none immediately after collection. New extraction selects supplied source/excerpt IDs; the application resolves exact fetched text/URL, while name, identity, ICP, confidence and quotation gates remain. Invalid cross-page/unknown IDs cannot create a lead.79 n8n tests pass. Follow-up CI/publication and final live batch pending; initial search/UI release3066c2e already deployed in DEV through38145264438. PR34 is open against develop and includes PR33 session changes. No production changes or sending.


### Company discovery DEV acceptance — 11 October 2026

Code `8b9d162dfdcc6301404bbbe0060399703a9f213b` passed full push CI `38145984359` and PR CI `38145987247`. DEV deployment [38146226265](https://github.com/geekedctrl/lorrysystem-deploy/actions/runs/38146226265) succeeded. Discovery and setup child workflows were published through the DEV n8n API with existing named credentials and workspace/lease headers preserved; the dispatcher resumed. All three workflows are active with current published versions and execution saving set to `none`.

A normal public-HTTPS admin login and LorrySystem workspace switch submitted the unchanged dashboard default query with a target of one company. Discovery job `960988f3-ffcb-4835-80e3-4084f9b2d07c` completed with `COMPANIES_ACCEPTED`, one new candidate and one accepted lead: **Hock Cheong**, `hockcheong.com.my`, lead `53f3592e-b375-4f7b-bb49-5c46be4d78d2`. A separate normal HTTP session verified the company in `/leads`, its detail page and `/discovered-leads?status=ALL`. Both test sessions logged out. The batch used one search, two fetches and one model call (4,932 input / 137 output tokens); recorded monetary cost is unavailable.

Follow-up research automatically ran and stopped at `NEEDS_REVIEW` / `SUPPORTED_CONTACT_REQUIRED`; discovery succeeded, but outreach preparation is not claimed complete. No outreach was approved or sent. The task-created retained diagnostic execution `21159` and temporary credential-bearing verifiers/raw diagnostic payload were removed after verification. User-owned compose/gitignore contents remain intact. PR [34](https://github.com/geekedctrl/lorrysystem-marketing-system/pull/34) targets `develop` and includes unmerged PR33's session repair to preserve the DEV baseline. Production and native-worker rollout are unchanged.


### Discovery rebuild discussion — 11 October 2026

User correction: discovered companies must await explicit human acceptance; automatic acceptance is no longer the desired policy. Both deployed `api/app/routers/automation.py` candidate ingestion and native `backend/marketing_backend/pipeline.py` discovery finalization currently create official leads automatically and schedule research. Both require revision before claiming manual-review behavior. The preceding successful one-company DEV test proves that one batch worked, not that discovery is broadly reliable.

Discussed direction: native Python discovery workers collect website evidence and use the existing xKiro adapter for catalog/ICP assessment. Reuse the existing queue/workspace/provider infrastructure. Proposed flow: search → bounded company-site crawl/extraction → evidence-backed assessment → candidate inbox → explicit Accept/Reject → accepted lead and research → remaining preparation → human outreach approval. Ordinary HTTP fetching and structured extraction first, browser rendering as a controlled fallback. Candidate-level failures, retryable discovery memory and visible stage counts are proposed reliability work. Search-provider choice and implementation scope remain discussion items; this entry changes documentation only and does not disable running workflows or alter records.


## Native discovery with manual review — 11 October 2026

Implemented on rebuild/manual-discovery: Brave website finding, guarded Python company crawling, Trafilatura extraction, optional guarded Playwright rendering and per-company xKiro assessments with numbered evidence excerpts. Discovery persists review candidates only. Explicit human Accept creates the lead/research run atomically and idempotently; Reject preserves the decision; targeted Reassess and retryable memory cover unavailable companies. Workspace RLS, catalog staleness, concurrent domain duplicate checks and native-worker lead INSERT denial guard the transition. Native dashboard/BFF adds candidate review, evidence, filters/paging and stage counts. Legacy ingestion, contract/export and summaries now also require human acceptance in source. See ../native-lead-discovery.md and the refreshed OpenAPI.

Acceptance: 50 PostgreSQL/backend tests, including actual Chromium network isolation, empty JavaScript shells and malformed links; nine BFF groups and the synthetic browser; an actual local browser/product form/BFF/restricted API/native worker manual acceptance test; actual two-product native API/worker acceptance; the legacy shared automation regression; 79 n8n checks; 13 login/session and five UX checks. Providers are synthetic. Local disposable projects discovery-review-test and discovery-legacy-test isolate fixtures. Live provider calibration/native DEV cutover and coordinated legacy n8n publication remain release work; no deployed executor changed and no outbound messages sent. Existing PR #33/#34 are now merged; latest develop `9e74818` adds separate frontend CSS. Preserve user-owned gitignore/compose; PR base develop.


Release checkpoint: implementation commit `bec7684`, integrated latest develop `9e74818` with merge `cf90bb9`; pushed branch `rebuild/manual-discovery`. Draft PR #36 targets develop: https://github.com/geekedctrl/lorrysystem-marketing-system/pull/36 . Keep draft until coordinated legacy guard/API publication or native cutover is ready; DEV has not been changed. GitHub CI is running. Local fixture projects `discovery-review-test` and `discovery-legacy-test`, their disposable volumes and the port 8098 gateway were removed after verification; pre-existing local stacks remain untouched. User-owned root compose/gitignore hashes remain unchanged and those edits are excluded.


Final legacy regression: the six-company fleet/accounting quality fixture explicitly accepts review candidates before processing research. Confirmed documented need reaches pending approval, existing-system/no-need stays below the opportunity threshold, missing contacts stop for review, and unsupported promises/cross-product access are refused. Mock SMTP regression passes using test transport only. Native discovery and backend checks passed on GitHub; the broader CI suite is rerunning with this corrected manual-acceptance fixture.


GitHub verification checkpoint: PR #36 at `b4efc70` passed Backend Rebuild CI (38153104959) and LorrySystem CI (38153104965), including native PostgreSQL/Chromium and the full legacy API/dashboard/quality/mock-SMTP suite. PR remains draft with base develop; coordinated release/native DEV cutover is pending. Local quality fixtures were removed again after the six-company regression.

Branch CI also passed at `b4efc70`: Backend Rebuild CI 38153101207 and LorrySystem CI 38153101223. All latest branch/PR checks are green.


## PR #36 DEV deployment - 12 October 2026

PR #36 merged to `develop` as `a599977292d17f1d67b8243f96383b543c30683d`. Develop CI run [38154347888](https://github.com/geekedctrl/lorrysystem-marketing-system/actions/runs/38154347888) passed; automatic DEV deployment [38154586326](https://github.com/geekedctrl/lorrysystem-deploy/actions/runs/38154586326) passed. Deployment record confirms exact target commit `a599977292d17f1d67b8243f96383b543c30683`; service health checks returned API 200 and dashboard 302.

Deployment scope: existing DEV compose still runs PostgreSQL, legacy Marketing API and legacy dashboard. `compose.backend.yml` is a separate native stack and was not added to the server deployment path; therefore the new Python discovery worker is not yet running in DEV. The deployed legacy API now requires manual candidate acceptance. The published DEV n8n guard was previously observed to expect the old shared-job value (`false`); it has not been synchronized or re-verified after this deploy. Direct API inspection returned Cloudflare Error 1010 `browser_signature_banned`, and the DietPi SSH jump was unreachable while the owner was away from the home network. Follow-up release work: verify/publish compatible n8n shared workflows and deploy/configure the native services before claiming native discovery is live. No live provider calls or emails were made.

## Current investigation — ITS ICP handoff and country targeting

The latest ITS scoring `Needs review` result was caused by a wrong ICP in the new preparation run, not a broken scoring stage: the accepted discovery memory correctly classifies ITS as `THIRD_PARTY_LOGISTICS`, while fresh preparation defaulted to the first alphabetical ICP, `MANUFACTURERS_DISTRIBUTORS`. A local fix now carries the accepted ICP into preparation. Discovery's Brave requests use `MY` as a region bias, which does not enforce geographic presence; local targeting queries now include the country name and distribute ICP profiles across targeted searches. Strict geography filtering remains undecided. See [14 October change log](2026-10-14-change-log.md). Local backend verification passed (57 tests; one optional Chromium check skipped). PR #46 merged to develop at f68e458; shared DEV deployment succeeded at 2026-10-14 02:33 UTC. The deployed worker source includes accepted ICP inheritance. Existing ITS history still shows the pre-fix MANUFACTURERS_DISTRIBUTORS run. A fresh authenticated preparation test has not yet been started; no new provider calls or messages were made.

### Post-deployment ITS verification

PR #46's deployed ICP handoff was verified with preparation run `1afe684c-2aca-4ab1-91d1-7b156fbff8d7`: RESEARCH carried `THIRD_PARTY_LOGISTICS`. Research/contact/scoring completed; scoring found relevance 60 but opportunity 0, and matching produced no supported product. The pipeline correctly stopped at `NEEDS_REVIEW` / `NO_SUPPORTED_PRODUCT_MATCH`; no draft or email was generated. Research identifies ITS as headquartered in Reno, Nevada with North American operations, making it unsuitable to validate Malaysia discovery. Next is a small discovery batch with human review for Malaysia evidence before acceptance.

### DEV discovery batch 467b9bab

Completed 3 Brave searches, 4 websites, 10 pages and 4 assessments; 2 candidates are ready for review, both Malaysian `THIRD_PARTY_LOGISTICS`: Hock Cheong (`hockcheong.com.my`) and BMT Group (`bmtgroup.com.my`). Official excerpts support Malaysia presence. Neither has been accepted, so no leads or preparation runs were created. Two assessed domains were unsupported, including a Singapore domain: the MY region bias is not a hard geographic filter. Provider usage: 3 searches and 4 model assessments (12,541 tokens); recorded search estimate $0.015 at configured rates, model pricing unconfigured. Human review is next; the batch did not yet validate ICP diversity.

### BMT research failure diagnosis and local fix

The backend-worker container did not restart (started 02:33:42 UTC, restart count 0). xKiro returned valid cached JSON; contact validation failed because two returned contact roles were non-string, causing the whole RESEARCH response to be discarded. A manual retry repeated the model request and same schema failure. Local fix validates contact entries independently, drops malformed people and preserves valid company findings. Regression passes: research completes, then reports `SUPPORTED_CONTACT_REQUIRED` for manual resolution. Backend suite: 58 passed, one optional Chromium check skipped. Fix is in PR #47 against develop; CI is pending and it is not deployed. No further live model calls during investigation.
