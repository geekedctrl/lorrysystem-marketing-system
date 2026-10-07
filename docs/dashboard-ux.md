# Dashboard UX redesign

Implemented on `feature/dashboard-ux-redesign`, 7 October 2026. The dashboard retains FastAPI/Jinja2, CSS and vanilla JavaScript. No database migration or provider/workflow changes are required for this redesign.

## Navigation and everyday work

The application shell groups Overview, Leads, Discovery, Outreach and Approvals separately from Product setup, Team and Settings/account. Workspace switching is available in the sidebar and checks existing membership and CSRF. Admin navigation is hidden for other roles; API permissions remain authoritative. The desktop sidebar collapses with named tooltips. On small screens it becomes a drawer with focus trapping, Escape dismissal and inert closed navigation. The account menu contains sign out and account settings.

Theme choices cycle System → Light → Dark. The initial theme follows the operating system; an explicit choice is stored in the browser. Both themes share semantic surface, text, border, feedback and focus tokens. Sign-in and invitation screens use the same theme. No external fonts, image providers or UI runtime dependencies are introduced.

## Screens and flows

| Screen | New behavior |
| --- | --- |
| Overview | Pending outreach review is the primary next action. Workspace automation health and failed/review jobs appear above recent records. Recent metrics describe the bounded sample rather than claiming lifetime totals. |
| Leads | Search, existing lifecycle/status/priority filters, newest/company/score sorting and 25-row pages. Preparation labels use current saved job/action state; approving a draft does not leave a historical awaiting-approval label. Parent links preserve the last list query in this browser tab. |
| Lead detail | Company and primary contact remain above a six-tab workspace: Overview, Research, People, Qualification, Outreach and Activity. Tabs support arrow/Home/End keys and remember the selected panel per browser tab. Existing section/source hash links reveal the appropriate panel. |
| Research and people | Company findings and source quality are separate from named people and their professional profiles. Shared evidence macros retain source quotes, confidence, ambiguity and verified public links. Contact/scoring controls live in Qualification; choosing a supported researched person remains in People. |
| Product setup | Three steps: details, catalog, review/activation. Back retains fields, step validation prevents skipping incomplete input, review is built as text (not injected HTML), and rejected API submissions preserve product/catalog fields. No unfinished setup is persisted until activation; there is no misleading Save draft action. Preferences, targeting and activity remain accessible. |
| Settings | Separate Product setup, Team, Connections and Account/workspaces sections. Existing integration controls remain disclosed under Connections. Admin/platform authorization is unchanged. Password changes and workspace creation are in Account/workspaces. |
| Approval | Message snapshot beside a sticky desktop decision panel. Approve is primary; change/rejection explanations are disclosed on demand. A link opens company/contact/qualification context. Approval explicitly remains separate from sending. |
| Outreach | Clearer name for marketing actions; filters and links to the associated lead's outreach panel. |
| Intake/import | Explicit parent controls, consistent forms and sticky action bars for long workflows. Existing CSV preview/commit and business-card extraction/review remain intact. |
| Errors/access | Shared styled recovery pages for account/workspace outages and role-restricted mutations, retaining HTTP error statuses. |

Sticky offsets track the actual header height, including wrapped company names. Tables scroll inside their container; cards/forms reflow on mobile. Focus styling, a skip link, form labels, status explanations and reduced-motion support are shared. Duplicate submission guards preserve submit-button action values. Automatic lead refresh avoids dirty forms and open dialogs, retaining the active tab and scroll position.

## Boundaries

This is the dashboard redesign, not a sending implementation. It does not activate n8n workflows, change scoring thresholds, broaden team access, enable bulk approval, add invented analytics or spend on live providers. Product activation in validation creates jobs only in the disposable local database. List preparation details fetch only the displayed page's records. Existing search/enrichment still uses the existing workspace API; large-dataset server-side search is a separate scaling improvement.

## Validation

- Disposable PostgreSQL/API/dashboard regressions: workspace access (183 checks), discovery, migration/rollback, company research, reviewed pipeline and shared automation.
- Eight research presentation checks and five preparation-state checks, including approved versus historical pending outcomes and resolved old failures.
- Browser checks at desktop, tablet and mobile sizes: routes, themes/persistence, tabs/keyboard/hash links, filtered parent navigation, drawer/Escape, actual setup activation/pause, validation retention, viewer access, approval without sending, empty states and horizontal overflow. Browser console has no errors.
- Dashboard Docker build and Python/JavaScript syntax checks.

Run state checks with `python dashboard/scripts/validate_ux_states.py`. CI runs these along with frontend JavaScript syntax and existing integration suites.

The browser runner requires Playwright and disposable native workflow fixture JSON (account plus workspace/lead fixtures). Keep this JSON ignored; it contains local test credentials. For a local Edge installation:

```powershell
python dashboard/scripts/validate_ux_browser.py --fixtures tmp/shared-native-fixtures.json --base-url http://127.0.0.1:8091 --api-url http://127.0.0.1:8011
```

On other systems use Playwright's installed Chromium or specify `--browser` with a local executable. Screenshots go to ignored `tmp/ux-review`. Never run the mutating browser test against a live workspace: it creates disposable accounts/products and may approve a test draft.

## Release

Local preview is `http://127.0.0.1:8091`. The release path is a feature PR into develop and user merge through existing CI/CD. No server deployment or n8n activation is performed by the redesign task.
