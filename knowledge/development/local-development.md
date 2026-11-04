# Local development and verification

Updated: 6 October 2026. Use a disposable workspace test environment for database-mutating regression scripts.

The former `compose.workspace-test.yml` stack has been removed. GitHub Actions
creates the disposable database and credentials for workspace integration checks.
Use `.github/workflows/ci.yml` as the current source for those checks. Do not run
database-mutating workspace tests against shared DEV or production data.

The regression suite requires `APP_ENV=ci` or `workspace-test`. It creates isolated fixture workspaces, companies and users. CI's [workflow](../../.github/workflows/ci.yml) defines the required checks and container setup.

For first-administrator bootstrap and migration instructions, use [the workspace deployment guide](../../docs/PRODUCT_WORKSPACES.md). Preserve user-owned uncommitted changes when preparing a feature branch. Read [the repository map](repository-map.md) to locate the relevant code.
