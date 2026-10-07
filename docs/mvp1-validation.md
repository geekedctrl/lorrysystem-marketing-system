# MVP1 DEV acceptance — 7 October 2026

SMTP tests are deferred at the user's request. No real email or prospect approval was performed.

| Product | Real company | Current observation |
| --- | --- | --- |
| LorrySystem | Kontena Nasional Berhad | New company accepted and researched. Following official leadership links improved the report to four named people. No supported reachable individual profile/email; stopped for contact review. |
| LorrySystem | Baiduri Dimensi Sdn Bhd | New company accepted and researched; stopped for a supported reachable contact. |
| LorrySystem | Quanterm Logistics (existing sample) | Current calibration is 25/100 with operational need 0 and buying signals 0. Existing GPS use is not an unmet need. Stopped below qualification threshold; earlier drafts remain history. |
| AIPath temporary test catalog | 3E Accounting PLT | Same shared workflow generated targeting, accepted the company and researched it. No named contact was confirmed in the available sources; stopped for supported contact review. Catalog is explicitly fictitious (Invoice Assist), authorized by the user for testing. |

Broad discovery searches returned no accepted companies in some batches. Targeted searches found the new samples above. Batch sizes are upper bounds, not guaranteed lead counts. The final Swift-targeted LorrySystem sample found no new suitable company. These results do not establish comprehensive market coverage or automatic outreach readiness.

## Changes from this validation

- Follow official management/board/founder/partner/contact links in one bounded second pass; maintain the existing total page-fetch budget and guarded public fetch.
- Normalize legal company suffixes in company/person search queries while retaining individual name, company affiliation and conflict checks.
- Require cited observed research facts for positive unmet-need/buying-signal points; remove unsupported points with an explicit explanation in n8n and API validation.
- Block approving stale generated drafts after research, score, contact or catalog changes, retaining history and request-changes/rejection controls. Recheck generated-draft context before future sending.

## Verification and remaining work

70 JavaScript tests, synthetic six-company API quality tests (including overstated opportunity points and stale approval protection), shared automation/pipeline regressions, and desktop/mobile stale-approval browser checks passed locally. Synthetic fixtures validate orchestration and safeguards, not real model interpretation. No SMTP test was run in this continuation. The temporary AIPath product is paused after its bounded tests.

The n8n research/validation changes are active in DEV. The new API approval/readiness and dashboard changes require the next PR deployment. Remaining acceptance work is broader supported contact coverage, fresh real matching/draft review, and later controlled email delivery. Do not declare MVP1 fully signed off while those checks are outstanding.
