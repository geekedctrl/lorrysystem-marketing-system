# Preparation reliability and controlled SMTP sending

Updated 7 October 2026. These features require API migrations 013 and 014 and the matching dashboard release.

Preparation uses shared workspace-aware n8n workflows. Workers see only the current research/stage attempt as an attention warning; earlier failures remain in history. Superseded attempts cannot be retried. Missing supported contacts stop preparation with a reason and a link to contact review. Slow work is flagged after five minutes queued or fifteen minutes running; a warning does not automatically restart it.

Scoring separates product relevance from documented unmet need and buying signals. Existing GPS or management software does not establish a replacement opportunity. Matching describes capability relevance, not purchase likelihood. Drafts acknowledge existing systems and ask an exploratory question. Evidence validation and unsupported-claim checks run before a draft reaches approval; human review remains necessary.

The Automation settings page shows shared worker heartbeat, the last observed search/model provider outcomes, seven-day request/token usage and optional cost estimates. Set AUTOMATION_SEARCH_USD_PER_REQUEST and AUTOMATION_LLM_INPUT_USD_PER_MILLION / AUTOMATION_LLM_OUTPUT_USD_PER_MILLION for estimates. Missing token reports or prices are labelled unavailable/partial; old jobs are not assigned fabricated costs. n8n sends usage only when the API advertises metrics support.

## SMTP setup and separate sending

A platform administrator must configure SMTP_CREDENTIAL_ENCRYPTION_KEY in the API container as a stable Fernet key, stored privately and backed up with the deployment secrets. Generate it privately with cryptography. Losing/changing this key requires reconnecting saved accounts. It must never be committed. Product administrators then configure the sender in Settings > Connections and verify its login. Verification sends no email. Only TLS port 465 and STARTTLS port 587 are supported; internal/private destinations are blocked. Saved passwords are encrypted and never returned by the API.

Approval does not send. A signed-in product administrator or operator must open the approved email, select a verified enabled sender, confirm, and press Send approved email. Shared automation/service credentials cannot send. The approved snapshot must match the current subject, body, contact and recipient; older approvals lacking a recipient snapshot must be reviewed again. Product recipient suppressions block handoff.

Delivery states distinguish SMTP acceptance from inbox delivery. Duplicate requests return the existing result. Known pre-acceptance failures allow an explicit new request, limited to three attempts. An uncertain connection loss during DATA or unresolved handoff blocks repeat sending to avoid duplicates; an administrator must check the provider externally. Bounce ingestion, inbox delivery confirmation, automatic unsubscribe processing, scheduling and automatic sending are not implemented.

## Validation and current limits

Local regressions use real PostgreSQL and workspace isolation with six synthetic companies across fleet/accounting products. Documented-need cases reach pending approval; existing-system/no-need cases stop below qualification threshold; missing contacts stop for review. SMTP uses a simulated transport and tests approval separation, immutable recipient/content, suppressions, human-only access, encryption/workspace binding, TLS ordering and duplicate prevention. No real email is sent.

The real DEV LorrySystem discovery tests returned no newly accepted companies. AIPath's DEV setup has an empty catalog/profile, so its real second-product test is pending actual offerings. Synthetic two-product regressions do not establish live research/draft quality or provider reliability. These limits must remain visible in release notes.
