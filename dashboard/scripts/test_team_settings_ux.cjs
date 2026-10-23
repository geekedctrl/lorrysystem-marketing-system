// Offline static regression checks; no provider/network/data writes.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const js = fs.readFileSync('dashboard/app/static/native.js','utf8');
const css = fs.readFileSync('dashboard/app/static/native.css','utf8');
for (const term of ['function teamMemberDisplay(', 'Status not provided', 'teamMemberDisplay).join', 'stillCurrent()', 'state.epoch', 'document.querySelector("#view") === view', 'Copy invitation code', 'navigator.clipboard.writeText(code)', 'target.replaceChildren()', 'if (!stillCurrent()) return;', 'Workspace administrators can invite members']) assert(js.includes(term),`Missing ${term}`);
assert(!js.includes('localStorage.setItem("invitation'), 'Invitation must not be persisted');
assert(!js.includes('console.log(invitation'), 'Invitation must not be logged');
assert(js.includes('request("members")') && js.includes('/invitations`'), 'Existing API routes missing');
assert(css.includes('@media (max-width:600px)') && css.includes('.team-member'), 'Responsive styling missing');
console.log('Team Settings synthetic static checks passed: member statuses, permissions, invitation one-time display, context guards, responsive styling.');
