# Contact resolution and preparation continuation

Admins and operators can resolve missing contacts in the lead's Qualification tab. Add a named contact, optional role, and either a published business email or individual HTTPS LinkedIn profile. A public source URL and explicit confirmation of company affiliation/channel are required. This is a human-reviewed entry, not an automatic verification claim; the app does not fetch the source during entry.

Saving creates an active contact and selects it as primary, with a review audit event containing its source. Existing contacts can also be selected and confirmed. Duplicate emails are rejected with an instruction to select the existing contact. Workspace boundaries and current-stage contact locks are enforced by the API. Viewers cannot change contacts.

Continue preparation requires an active product plan, verified usable company research, and a reviewed named reachable primary contact. It queues shared scoring; existing automation then qualifies, matches and drafts according to the score/evidence, stopping at human approval. Repeated requests reuse pending/running scoring work. The supported-contact warning on that research attempt is cleared only after continuation queues successfully; history is retained. Missing research, paused automation or unsupported contact blocks continuation. No sending is triggered.

API: POST /api/leads/{id}/contact-review accepts a manual object (full_name, job_title, email, linkedin_url, source_url) with confirmed:true; mutually exclusive with research-person/existing-contact selection. POST /api/leads/{id}/continue-preparation queues managed scoring.

Validation: two-product disposable API tests cover manual review, missing-channel stop, malformed email/private source rejection, foreign workspace denial, duplicates and repeated continuation. Existing pipeline regression passes. Desktop/mobile form checks pass without overflow or browser errors. No live SMTP or real contact changes were performed.
