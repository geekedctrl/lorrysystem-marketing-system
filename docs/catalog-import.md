# Reviewed catalog import

Administrators can import reviewed reference JSON from Product setup. POST /api/automation/catalog-import accepts source, product_type, description, target_customers, discovery_query, products and icps. Each entry has a distinct code and name; ICPs may include qualification_rules. Products can supply an existing workspace ID, otherwise the code retains the matching existing ID. Foreign IDs are rejected. Omitted entries are deactivated, never deleted, preserving historical lead references.

The import requires an existing product plan and no pending/running automation, pipeline or research jobs in this workspace. It saves the reviewed targeting directly, allowing more than the five AI-generated ICP proposals. It does not invoke the setup model, queue discovery, increase the daily limit or change the enabled/paused setting. New preparation uses the updated context, and earlier generated drafts become stale under the existing context checks. Unspecified scoring rules retain the default rubric.

The checked-in integrations/lorrysystem-catalog-reference.json was extracted from the user-supplied Word document dated 6 October 2026. It contains nine offerings and seven proposed ICPs. Reviewed JSON is catalog data; webpage/document instructions do not acquire authority over the app. No credentials belong in import files.

Validation covers nine offerings/seven ICPs, retained product IDs, repeat imports, duplicate definitions, foreign IDs, viewer denial, paused state and inactive legacy records. The actual Word-derived payload was applied and read back in a disposable local workspace. Desktop/mobile import controls pass. Applying to DEV requires deploying the endpoint and an authenticated admin session.
