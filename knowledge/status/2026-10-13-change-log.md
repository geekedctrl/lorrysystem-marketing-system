# 13 October 2026 change log

## Native preparation research reliability

- Diagnosed a real accepted DEV lead whose research job failed after a successful xKiro call; no later stages were queued.
- The saved model response exceeded the five-person schema limit and contained one unsupported fact citation. Extra people now get capped; unsupported individual evidence is omitted with an explicit research note while valid facts continue.
- Prompt now asks for at most five public contacts, and stage schema failures use `MODEL_OUTPUT_SCHEMA_INVALID`.
- Added a PostgreSQL-backed regression for extra people and unsupported citations. Full suite: 54 passed, one optional Chromium case skipped.
- Code/docs are local and release/retry are pending. n8n remains available until a real preparation run passes through pending human approval.
