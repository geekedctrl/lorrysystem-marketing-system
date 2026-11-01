# GitHub changes and DEV deployment

Updated: 6 October 2026.

Implement changes on a focused feature/fix branch, run the relevant checks, push it and open a PR against `develop`. The user reviews and merges that PR. Do not substitute a manual server edit or merge for the agreed process.

The [CI workflow](../../.github/workflows/ci.yml) verifies API, database, dashboard and n8n adaptation. A successful push build on `develop` triggers [deployment dispatch](../../.github/workflows/develop-deploy-dispatch.yml) to the separate `geekedctrl/lorrysystem-deploy` repository. Feature-branch CI alone does not deploy the development server.

Verify the merged SHA and deployment outcome before declaring a feature deployed. An API change can be merged while the server still runs the preceding version.

Live n8n workflows and their credential store are managed separately from application images. Workflow changes require a reviewed binding to the correct workspace, preserved credential references and a published active version. Never export credential values to a tracked file. Research/industry updates sometimes need a fresh research run after API/dashboard deployment to populate existing leads.

The `knowledge/` folder is currently ignored by Git. Its local reorganization is not included in application PRs unless the user separately decides to version it. Tracked implementation docs live under `docs/` and `integrations/n8n/`.
