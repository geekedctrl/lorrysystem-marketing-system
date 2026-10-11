# Dashboard sign-in recovery

## Problem and behavior

The deployed legacy dashboard rejected stale or missing login CSRF tokens with a bare HTTP 403 saying to reload. Reloading that page resubmitted the same password POST and invalid token, leaving the user stuck. Fresh cookie-jar GET requests on DEV did return a stable token; the initial cause of the user's browser/session mismatch was not observable from the server. The HTTPS ingress returned `Cache-Control: no-store` and Cloudflare `DYNAMIC`, rather than a cached form.

Rejected login submissions now return HTTP 303 to `/login?notice=session-expired`. The GET renders a usable form and an explanation. Submitted credentials are not forwarded to the account API or replayed during recovery. Missing form tokens follow the same recovery path. Password errors still appear on the login form; other state-changing routes retain their CSRF checks.

The legacy dashboard's signed, HttpOnly, host-only cookie is now named `marketing_dashboard_session`, replacing Starlette's generic `session`. Generic cookies from other applications cannot shadow it. This is preventive isolation; an actual cookie collision in the user's browser has not been confirmed. Existing users must sign in once after this change. No existing API accounts, passwords, workspace memberships or signing keys are changed. The independent native frontend continues using its own `native_session` cookie.

## Verification

Run `python dashboard/scripts/validate_login_sessions.py` with dashboard requirements installed. Ten synthetic HTTP tests cover normal login/session rotation, stale forms, missing cookies/tokens, foreign-browser tokens, damaged signatures, duplicate generic cookies, password errors, protected logout and untrusted notices. API calls are mocked and no external messages or provider calls occur. CI runs this suite alongside the existing dashboard and workspace checks.

DEV release verification and the associated PR/deployment runs are recorded in `docs/ai/TEST_STATUS.md`. Public ingress checks must use an accepted browser user agent; unrecognized agents can receive a Cloudflare 403 before reaching the dashboard. Cookie and credential values must not be logged.
