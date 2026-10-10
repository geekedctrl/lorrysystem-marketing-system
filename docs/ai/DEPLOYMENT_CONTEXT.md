# Deployment context

Application baseline inspected: 9c0a3b0f03306d399ba9ee76ab14a8be37e7ed09 (develop).
Deployment repository: https://github.com/geekedctrl/lorrysystem-deploy
main inspected SHA: cba785acbb4da43a135da4a6bc06d1bfb94cda40.

Automatic DEV workflow independently verifies successful push CI on develop and exact application SHA, checks lorryrunner, invokes restricted /usr/local/sbin/lorry-dev-deploy and verifies health/deployment record. Last observed workflow success: 2026-10-08 10:20 MYT; current deployed application SHA was not inspected. Workflow SHA is not the deployed application SHA.

Manual DEV workflow allows develop and feature/fix/chore branches; codex/campaign-strategist is excluded. Application push CI also excludes codex/*; PRs to develop run CI. No workflow changes are needed to review this PR. No deploy triggered here.

Runner smoke workflow tests Docker/sudo/direct DEV/PROD write denial. Actual host helper, sudoers, environment protections, PROD configuration and runtime state remain unverified. No infrastructure modifications made. Preserve restricted runner and DEV/PROD separation.
