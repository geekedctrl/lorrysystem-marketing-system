# DEV runner clock recovery — 11 October 2026

The deployment repository is `geekedctrl/lorrysystem-deploy`. Automatic deployments consume successful `develop` CI only. Production remains a separate release decision.

## Incident

Run 38122758117 stayed queued because runner `lorrysystem-dev-deploy` was offline. Its Linux service is `actions.runner.geekedctrl-lorrysystem-deploy.lorrysystem-dev-deploy.service`, installed in `/opt/lorrysystem/ops/actions-runner` and running as `lorryrunner`.

The terminal message claimed the runner registration was deleted. The detailed `_diag/Runner_*.log` instead revealed an OAuth token expiration error: DietPi system time was approximately 51 minutes 50 seconds behind GitHub. Hardware clock matched current UTC, but system time was not synchronized. DietPi `CONFIG_NTP_MODE=2` (boot plus daily) had stopped systemd-timesyncd after boot.

## Recovery performed

- Connected through `ubuntu@192.168.1.120` to DietPi root on forwarded port 2223.
- Preserved stale `.runner_migrated`, credentials and RSA parameters in a root-only registration backup directory; did not copy secrets into this repository.
- Used a fresh GitHub registration token privately and registered the existing installation as `lorryrunner`, preserving name `lorrysystem-dev-deploy` and custom label `lorrysystem-dev`.
- Installed the systemd service for `lorryrunner` and enabled its startup at boot.
- Enabled NTP using `timedatectl set-ntp true`. Synchronization corrected the clock and the runner connected.
- Persisted continuous time synchronization using `/boot/dietpi/func/dietpi-set_software ntpd-mode 4` (daemon and drift mode).
- Confirmed synchronized system time, active NTP and enabled runner service. GitHub showed runner online and busy; the queued deployment resumed automatically.

## Future diagnostics

Check `timedatectl status`, `timedatectl timesync-status`, the runner service journal, and the detailed runner diagnostic exception before interpreting a generic registration-deleted message. If authentication failed due to time skew, fix synchronization before attempting another registration. Do not print credential files or registration tokens.

If local re-registration is necessary, `.runner_migrated` can also retain stale configuration; clearing only `.runner` was insufficient with this installation. Stop the service first and preserve registration files privately.

## Final verification

Deployment run 38122758117 completed successfully, including deployment record and DEV service checks. Runner remains active; synchronized time and continuous NTP verified.
