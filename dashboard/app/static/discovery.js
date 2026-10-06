'use strict';
(() => {
  const form = document.getElementById('find-leads-form');
  const button = document.getElementById('find-leads-button');
  form?.addEventListener('submit', () => {
    button.disabled = true;
    button.textContent = 'Starting discovery…';
  });
  const status = document.getElementById('discovery-run-status');
  if (!status || !['QUEUED', 'RUNNING'].includes(status.dataset.status)) return;
  async function poll() {
    try {
      const response = await fetch('/discovered-leads/discovery-status', {cache: 'no-store', redirect: 'error'});
      if (response.status === 401 || response.status === 403) return;
      if (response.ok) {
        const runs = await response.json();
        const run = runs.find(item => item.id === status.dataset.runId);
        if (!run) {
          window.location.assign('/discovered-leads');
          return;
        }
        if (run && !['QUEUED', 'RUNNING'].includes(run.status)) {
          // Retain the selected workspace, but clear old list filters so fresh
          // candidates are visible after a run finishes.
          window.location.assign('/discovered-leads');
          return;
        }
      }
    } catch (_) {
      // Temporary network failures do not start a second run.
    }
    setTimeout(poll, 4000);
  }
  setTimeout(poll, 4000);
})();
