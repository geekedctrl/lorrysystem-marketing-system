// Synthetic-only checks. No browser, backend, accounts, or providers contacted.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../app/static/native.js'), 'utf8');
const start = source.indexOf('  // Read-only, display-only status descriptions.');
const end = source.indexOf('  const empty =', start);
assert.ok(start >= 0 && end > start, 'status mapping exists');
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const sandbox = { esc: escapeHTML };
vm.runInNewContext(source.slice(start, end).replaceAll('const connectionStatus =', 'var connectionStatus =').replaceAll('const connectionRow =', 'var connectionRow ='), sandbox);
for (const [input, label] of [['CONFIGURED','Configured'],['UNVERIFIED','Unverified'],['UNAVAILABLE','Unavailable'],['DISABLED','Disabled'],['VERIFIED','Verified'],['SOMETHING_NEW','Other status'],[null,'Other status']]) {
 assert.match(sandbox.connectionStatus(input), new RegExp(label));
}
assert.doesNotMatch(sandbox.connectionStatus('<script>alert(1)</script>'), /<script>/);
assert.doesNotMatch(sandbox.connectionRow('<img src=x onerror=alert(1)>','DISABLED'), /<img/);
assert.match(sandbox.connectionStatus('CONFIGURED'), /does not mean it was tested/);
const branch = source.slice(source.indexOf('} else if (section === "connections")'), source.indexOf('view.innerHTML = settingsNav() + html;', source.indexOf('} else if (section === "connections")')));
assert.match(branch, /request\("connections"\)/);
assert.match(branch, /request\("senders"\)/);
assert.doesNotMatch(branch, /data-command=|data-sender|senders\/\$\{.*\/verify|field\("secret"|field\("password"/);
assert.match(source, /Connection information is unavailable right now/);
console.log('Connections UX synthetic tests passed: states, unknown, XSS escaping, read-only, error fallback.');
