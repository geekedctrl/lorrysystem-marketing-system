# Native frontend backend support

Implemented locally on 11 October 2026 on rebuild/native-frontend-support, based on merged PR #29. Portable implementation guide: [native frontend backend support](../../docs/native-frontend-backend-support.md).

BE-01–BE-06 are implemented: isolated local frontend/API/database/worker integration; guarded two-product/four-role synthetic fixtures; actual browser acceptance; typed responses/auth capabilities; single-lead and keyset paging; immutable human revisions with a separate reviewer; soft catalog lifecycle/versioning and explicit partial setup retries. Worker-loop scheduling gap fixed.

37 PostgreSQL tests, actual restricted HTTP API/BFF/worker acceptance, headless Edge two-product/form/preparation/approval/tablet/mobile checks and restricted API revision/lifecycle checks passed. Rebuild API/worker smoke also passes without provider calls. OpenAPI and normalized synthetic examples refreshed. Windows Docker forwarding remains defective; the tested loopback-only gateway provides localhost8095 without machine-wide networking changes.

Frontend owner retains its files in geekedctrl/redesign-frontend. New route allowlists/query forwarding/revision/lifecycle UI and nonzero unavailable_queries count rendering are required adaptations. Team/provider/import/sending/migration and shared production sessions remain separate slices. No paid provider calls, prospect messages, DEV deployment or n8n cutover. New work local, not pushed/deployed; PRs target develop.
