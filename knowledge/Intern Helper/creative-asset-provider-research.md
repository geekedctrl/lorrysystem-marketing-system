# Intern Task: Research Affordable Poster and Video Generation APIs

## Assignment details

| Field | Details |
| --- | --- |
| **Task ID** | INT-2026-10-14-01 |
| **Task title** | Research affordable APIs for marketing posters and short videos |
| **Assigned to** | [Intern name] |
| **Assigned by** | PKartikean (project lead) |
| **Date allocated** | 14 October 2026 |
| **Due date** | [Set due date] |
| **Priority** | Normal — research needed before the creative-generation worker stage |
| **Status** | Assigned |
| **Project** | LorrySystem Marketing System — native Python workers |
| **Deliverable** | Research report and non-production Python examples; no production integration |

## Objective

Find affordable, dependable services that our native Python workers could call to generate marketing posters and short promotional videos. Read the providers’ official API and pricing documentation and make a recommendation that lets the team implement these stages later without repeating the research.

The system will eventually generate creative assets and email drafts for different product workspaces. Workspace users should not need to configure n8n or provide model-provider API keys. Keep this task to research and examples; do not change the application or worker pipeline.

## Research scope

Compare at least **three image-generation options** and **three video-generation options**. A provider can appear in both categories if it offers both. Consider hosted model platforms and model-specific APIs. Evaluate cost alongside output quality, control, reliability, and integration effort; do not choose solely by headline price.

Prioritize services with a documented server-side API, clear commercial terms, asynchronous job support for longer video requests, and a practical way to retrieve generated files.

## What to investigate for every provider/model

### Product and output capabilities

- Provider name, exact model, and official endpoint.
- Image or video capabilities; supported dimensions, aspect ratios, resolution, and video duration.
- Prompt controls, negative prompts, reference-image or image-to-video support, and logo/brand asset handling.
- Whether the output is suitable for social-media posters and short product-promotion clips.

### Pricing and limits

- Official unit pricing, including resolution, duration, quality, or other multipliers.
- Subscription, minimum balance, credit, storage, or other charges that affect the real cost.
- Rate limits and relevant request/payload limits.
- Estimate a comparable cost for:
  - One social poster.
  - One 5-second video at a stated resolution/quality.
  - A batch of 100 posters and 100 five-second videos.
- Link to the official pricing page and record the date checked. Mark estimates clearly when pricing is variable, credit-based, or not published as a fixed rate. Do not infer a precise price from marketing copy.

### API and Python integration

- Link to the official API docs, authentication docs, and SDK docs if applicable.
- Authentication header and environment variable name to use in an example.
- Exact endpoint or SDK call, required fields, and a representative response shape.
- State whether generation is synchronous or asynchronous.
- For asynchronous jobs, explain submission, polling or webhook completion, timeout handling, and failed-job behavior.
- Explain how to download and save the generated output. Note whether result URLs expire.
- Include a minimal Python request example. Use environment variables for credentials, set network timeouts, handle HTTP/provider errors, and never print secrets.

### Terms and operational risks

- Commercial-use, ownership, attribution, and watermark terms, citing official terms.
- Retention and privacy: what happens to prompts, reference images, and generated files.
- Content restrictions relevant to ordinary B2B marketing.
- Idempotency or duplicate-generation/charge risks when retrying.
- Any stability, availability, or vendor lock-in concerns stated in the docs.

## Architecture recommendation for our workers

Propose how image/video requests should fit into our native worker architecture. Address:

- Whether poster and video generation should be separate queued job kinds, and why.
- Job lifecycle/progress states from queued through provider submission, generation, download, and completion/review.
- Safe retry behavior that does not accidentally create duplicate paid generations.
- Which metadata to persist: workspace, provider/model, prompt/version, provider job ID, estimated/actual cost if available, output format/dimensions/duration, storage key, and sanitized failure reason.
- How the dashboard should reference assets and how long provider URLs can be trusted.
- Why generated files should normally be copied to our own object storage rather than treated as permanent provider-hosted assets.
- How platform-managed credentials, provider outages, rate limits, and workspace/platform budget limits should be handled.
- Where email fits: whether image/video are attachments or links in a later approved email draft, and what should remain a separate human-approved sending action. Do not design or implement sending in this task.

Keep this recommendation provider-neutral where possible, so switching vendors does not require changing workspace-facing product setup.

## Prototype expectations

For the strongest image candidate and strongest video candidate, provide a small **non-production** Python proof of concept that:

1. Reads the API key from an environment variable.
2. Submits one generation request using a clearly labeled example prompt.
3. Handles the provider’s sync or async response correctly.
4. Downloads/saves the result to a local output directory.
5. Uses timeouts and gives useful sanitized error messages.

Do not run a paid generation. If a live request is needed to verify behavior, document the exact command and expected charge, and wait for approval. Never commit API keys, real customer data, or generated credentials.

## Deliverables and location

Create a Markdown report in `knowledge/Intern Helper/` named `creative-asset-provider-research-report.md`. It should contain:

1. An executive recommendation: one preferred image provider and one preferred video provider, with tradeoffs and a fallback option.
2. Separate comparison tables for image and video candidates.
3. Official documentation/pricing/terms links beside the claims they support.
4. Comparable cost estimates and assumptions.
5. Python request/response examples and async lifecycle notes.
6. The proposed worker integration outline and key risks/open questions.
7. The date each provider’s docs and pricing were checked.

Put proof-of-concept code in a separate clearly labeled non-production subfolder or code block. Update `knowledge/README.md` with a link to the report once it exists. Keep the report readable and decision-oriented; use appendices for longer API payloads.

## Out of scope

- Production code, schema changes, worker changes, dashboard changes, or deployment.
- Selecting or purchasing a plan, creating provider accounts, or entering payment details.
- Making paid API calls or using real workspace/customer information.
- Sending emails or publishing generated assets.
- Storing secrets in source control or in the report.

## Completion checklist

- [ ] At least three image and three video options compared.
- [ ] Key price, API, and terms statements linked to official provider documentation.
- [ ] Cost calculations state units, quality/resolution/duration, assumptions, and date checked.
- [ ] Both recommended providers have adaptable Python request examples.
- [ ] Async polling/webhook, timeout, retry, download, and URL-expiry behavior documented where applicable.
- [ ] Worker architecture proposal covers idempotency, storage, credentials, budgets, and failures.
- [ ] No paid requests, secrets, production changes, or customer data used.
- [ ] Report saved under `knowledge/Intern Helper/` and linked from `knowledge/README.md`.

## Update log

| Date | Update |
| --- | --- |
| 14 October 2026 | Assignment created; intern name and due date left for the project lead to fill in. |
