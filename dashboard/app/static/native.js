/* Native API dashboard. All provider content is escaped; tokens stay in the BFF. */
(() => {
  "use strict";
  const app = document.querySelector("#app");
  const state = {
    csrf: "",
    workspaces: [],
    workspace: null,
    page: "overview",
    lead: null,
    tab: "Overview",
    epoch: 0,
    dirty: false,
    busy: false,
    controller: new AbortController(),
    data: {},
    setup: null,
    timer: null,
    user: null,
    leadFilters: { q: "", status: "", cursor: null, previous: [] },
    candidateFilters: { status: "READY_FOR_REVIEW", offset: 0 },
  };
  const esc = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const label = (value) =>
    String(value ?? "Not available")
      .replaceAll("_", " ")
      .toLowerCase()
      .replace(/^./, (c) => c.toUpperCase());
  const badge = (value) =>
    `<span class="badge ${["NEEDS_REVIEW", "FAILED", "STALE", "PENDING_APPROVAL"].includes(value) ? "attention" : ["APPROVED", "COMPLETED"].includes(value) ? "success" : ""}">${esc(label(value))}</span>`;
  const empty = (text) => `<p class="empty">${esc(text)}</p>`;
  const card = (title, body) =>
    `<section class="card"><h2>${esc(title)}</h2>${body}</section>`;
  const canWork = () => ["ADMIN", "OPERATOR"].includes(state.workspace?.role);
  const canReview = () => ["ADMIN", "REVIEWER"].includes(state.workspace?.role);
  const canReviewCandidate = () =>
    ["ADMIN", "OPERATOR", "REVIEWER"].includes(state.workspace?.role);
  const isAdmin = () => state.workspace?.role === "ADMIN";
  const uid = () => crypto.randomUUID();
  const url = (value) => {
    try {
      const u = new URL(value);
      if (
        !["http:", "https:"].includes(u.protocol) ||
        u.username ||
        u.password ||
        !u.hostname.includes(".") ||
        /^(localhost|127\.|10\.|192\.168\.|169\.254\.|0\.)|\.(local|internal|localhost)$/.test(
          u.hostname,
        ) ||
        /^172\.(1[6-9]|2\d|3[01])\./.test(u.hostname) ||
        u.hostname.includes(":")
      )
        return null;
      return u.href;
    } catch {
      return null;
    }
  };
  const link = (value, text = "View source") =>
    url(value)
      ? `<a class="source" href="${esc(url(value))}" target="_blank" rel="noopener noreferrer">${esc(text)} ↗</a>`
      : `<span class="muted">Source link unavailable</span>`;
  const evidence = (values) =>
    (values || [])
      .map(
        (v) =>
          `<details><summary>${link(v.source_url)} · Evidence</summary><blockquote>${esc(v.evidence_quote)}</blockquote></details>`,
      )
      .join("");
  const productName = (code) =>
    state.data.catalog?.find((p) => p.code === code)?.name ||
    code ||
    "Not selected";
  let noticeTimer;
  const notice = (text) => {
    clearTimeout(noticeTimer);
    document.querySelector("#notice").textContent = text;
    if (text)
      noticeTimer = setTimeout(() => {
        document.querySelector("#notice").textContent = "";
      }, 6000);
  };
  function resetRequests() {
    state.epoch++;
    state.controller.abort();
    state.controller = new AbortController();
    clearTimeout(state.timer);
  }
  async function request(path, method = "GET", payload, session = false) {
    const epoch = state.epoch;
    const response = await fetch(
      session
        ? path
        : `/gateway/${encodeURIComponent(state.workspace.id)}/${path}`,
      {
        method,
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": state.csrf,
          "X-Native-Request": "1",
        },
        body: payload === undefined ? undefined : JSON.stringify(payload),
        signal: state.controller.signal,
      },
    );
    const data = await response.json();
    if (epoch !== state.epoch)
      throw new DOMException("Workspace changed", "AbortError");
    if (!response.ok) {
      if (
        response.status === 401 &&
        path !== "/session/login" &&
        path !== "/session"
      ) {
        resetRequests();
        state.data = {};
        state.workspace = null;
        state.dirty = false;
        login("Your session expired. Sign in again.");
      }
      let detail = data.detail;
      if (Array.isArray(detail))
        detail = detail
          .map((x) => `${x.loc?.slice(1).join(".") || "Field"}: ${x.msg}`)
          .join(" · ");
      const error = new Error(
        typeof detail === "string"
          ? detail
          : {
              403: "Your role does not permit this action.",
              404: "This record is unavailable.",
              409: "Context changed. Refresh and review again.",
              429: "Too many sign-in attempts. Try again later.",
            }[response.status] || "Unable to complete the request.",
      );
      error.status = response.status;
      throw error;
    }
    return data;
  }
  const field = (name, title, value = "", attrs = "", type = "text") => {
    const id = uid();
    return `<label for="${id}">${esc(title)}</label><input id="${id}" name="${esc(name)}" type="${type}" value="${esc(value)}" ${attrs}>`;
  };
  const area = (name, title, value = "", attrs = "") => {
    const id = uid();
    return `<label for="${id}">${esc(title)}</label><textarea id="${id}" name="${esc(name)}" ${attrs}>${esc(value)}</textarea>`;
  };
  function login(message = "") {
    state.user = null;
    state.leadFilters = { q: "", status: "", cursor: null, previous: [] };
    state.candidateFilters = { status: "READY_FOR_REVIEW", offset: 0 };
    state.page = "overview";
    state.lead = null;
    state.tab = "Overview";
    state.setup = null;
    state.dirty = false;
    notice("");
    app.innerHTML = `<main id="content" class="login" tabindex="-1"><div class="brand">Marketing<small>A clear path from product to proposal</small></div><section class="card"><h1>Welcome back</h1><p class="muted">Sign in to your product workspaces.</p><form id="login-form">${field("email", "Email", "", "required autocomplete=username", "email")}${field("password", "Password", "", "required autocomplete=current-password", "password")}<div class="error" role="alert" ${message ? "" : "hidden"}>${esc(message)}</div><div class="actions"><button class="primary">Sign in</button><button type="button" data-theme>Change theme</button></div></form></section></main>`;
    document.querySelector("#login-form").onsubmit = async (event) => {
      event.preventDefault();
      const form = event.target,
        button = form.querySelector("button");
      button.disabled = true;
      try {
        await request(
          "/session/login",
          "POST",
          Object.fromEntries(new FormData(form)),
          true,
        );
        await boot();
      } catch (error) {
        form.querySelector(".error").hidden = false;
        form.querySelector(".error").textContent = error.message;
        button.disabled = false;
      }
    };
  }
  function shell() {
    app.innerHTML = `<div class="native-shell"><aside class="native-sidebar" id="sidebar" aria-label="Workspace navigation"><div class="brand">Marketing<small>Product operations</small></div><div class="workspace-controls"><label for="workspace">Product workspace</label><select id="workspace">${state.workspaces.map((w) => `<option value="${esc(w.id)}" ${w.id === state.workspace?.id ? "selected" : ""}>${esc(w.name)}</option>`).join("")}</select><p class="muted">${esc(label(state.workspace?.role))}</p></div><nav>${[["overview", "Overview"], ["leads", "Leads"], ["discovery", "Discovery"], ["approvals", "Approvals"], ["operations", "Activity & operations"], ...(isAdmin() ? [["setup", "Product setup"]] : [])].map(([p, t]) => `<a href="#${p}" data-page="${p}" ${state.page === p ? "aria-current=page" : ""}>${esc(t)}</a>`).join("")}</nav><footer><small class="account-identity">${esc(state.user?.email || "")}${state.user?.capabilities?.create_workspace ? " · Platform administrator" : ""}</small><button data-theme>Theme: ${esc(localStorage.getItem("marketing-theme") || "system")}</button><button id="collapse">Collapse navigation</button><button id="logout">Sign out</button></footer></aside><div class="scrim" hidden></div><main id="content" class="native-main" tabindex="-1"><div class="page-top"><div><div class="eyebrow">${esc(state.workspace?.name)}</div><h1 id="heading">${esc(state.page === "lead" ? "Lead workspace" : label(state.page))}</h1></div><button class="mobile-menu" aria-controls="sidebar" aria-expanded="false">Menu</button></div><div id="view" aria-live="polite"></div></main></div>`;
    document.querySelector("#workspace").onchange = async (e) => {
      const previous = state.workspace.id;
      if (
        state.busy ||
        (state.dirty &&
          !confirm("Leave your unsaved changes and switch workspace?"))
      ) {
        e.target.value = previous;
        return;
      }
      resetRequests();
      state.data = {};
      state.setup = null;
      state.dirty = false;
      state.lead = null;
      state.page = "overview";
      state.leadFilters = { q: "", status: "", cursor: null, previous: [] };
      state.candidateFilters = { status: "READY_FOR_REVIEW", offset: 0 };
      notice("");
      document.querySelector("#view").innerHTML = empty("Switching workspace…");
      try {
        const data = await request(
          "/session/workspace",
          "POST",
          { workspace_id: e.target.value },
          true,
        );
        state.workspace = data.workspace;
        state.csrf = data.csrf;
        history.replaceState(null, "", "#overview");
        shell();
        await load();
      } catch (error) {
        if (error.name !== "AbortError") {
          notice(error.message);
          await boot();
        }
      }
    };
    document.querySelector("#logout").onclick = async () => {
      try {
        await request("/session/logout", "POST", undefined, true);
        resetRequests();
        state.data = {};
        state.csrf = "";
        state.workspace = null;
        login();
      } catch (error) {
        notice(error.message);
      }
    };
    document.querySelector("#collapse").onclick = () =>
      document.querySelector(".native-shell").classList.toggle("collapsed");
    const menu = document.querySelector(".mobile-menu"),
      sidebar = document.querySelector("#sidebar"),
      scrim = document.querySelector(".scrim");
    const close = () => {
      sidebar.classList.remove("open");
      scrim.hidden = true;
      menu.setAttribute("aria-expanded", "false");
      document.querySelector("#content").inert = false;
      menu.focus();
    };
    menu.onclick = () => {
      sidebar.classList.add("open");
      scrim.hidden = false;
      menu.setAttribute("aria-expanded", "true");
      document.querySelector("#content").inert = true;
      sidebar.querySelector("select").focus();
    };
    scrim.onclick = close;
    sidebar.onkeydown = (e) => {
      if (e.key === "Escape") close();
      if (e.key === "Tab" && sidebar.classList.contains("open")) {
        const items = [...sidebar.querySelectorAll("a,button,select")].filter(
            (x) => x.offsetParent !== null,
          ),
          first = items[0],
          last = items.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
  }
  async function boot() {
    try {
      const info = await request("/session", "GET", undefined, true);
      state.csrf = info.csrf;
      state.workspaces = info.workspaces;
      state.user = info.user;
      if (!info.workspaces.length) {
        app.innerHTML = `<main id="content" class="login">${card("No workspace access", "<p>Ask your administrator to grant access to a product workspace.</p><button id='empty-logout'>Sign out</button>")}</main>`;
        document.querySelector("#empty-logout").onclick = async () => {
          await request("/session/logout", "POST", undefined, true);
          login();
        };
        return;
      }
      const wid =
        info.workspace_id &&
        info.workspaces.some((w) => w.id === info.workspace_id)
          ? info.workspace_id
          : info.workspaces[0].id;
      const selected = await request(
        "/session/workspace",
        "POST",
        { workspace_id: wid },
        true,
      );
      state.workspace = selected.workspace;
      state.csrf = selected.csrf;
      shell();
      await load();
    } catch (error) {
      if (error.name !== "AbortError")
        login(error.status === 401 ? "" : error.message);
    }
  }
  async function navigate(page, lead = null) {
    if (state.busy) return;
    if (state.dirty && !confirm("Leave your unsaved changes?")) return;
    resetRequests();
    state.dirty = false;
    state.page = page;
    state.lead = lead;
    state.tab = "Overview";
    history.replaceState(null, "", `#${page}${lead ? "/" + lead : ""}`);
    shell();
    await load();
    document.querySelector("#content")?.focus();
  }
  async function load(poll = false) {
    const view = document.querySelector("#view"),
      epoch = state.epoch;
    if (!view) return;
    if (!poll) view.innerHTML = empty("Loading workspace records…");
    try {
      const query = new URLSearchParams({ limit: "25" });
      const filters = state.page === "leads" ? state.leadFilters : {};
      if (filters.q) query.set("q", filters.q);
      if (filters.status) query.set("status", filters.status);
      if (filters.cursor) query.set("cursor", filters.cursor);
      const [operations, leadPage, approvals, jobs, catalog, allCatalog] =
        await Promise.all([
          request("operations"),
          request(`leads/page?${query}`),
          request("approvals"),
          request("jobs"),
          request("catalog"),
          isAdmin() ? request("catalog/all") : Promise.resolve([]),
        ]);
      let runs = [],
        leadDetail = null;
      if (state.page === "lead")
        [runs, leadDetail] = await Promise.all([
          request(`leads/${encodeURIComponent(state.lead)}/preparation`),
          request(`leads/${encodeURIComponent(state.lead)}`),
        ]);
      const candidates =
        state.page === "discovery"
          ? await request(
              `candidates?${new URLSearchParams({ limit: "25", offset: String(state.candidateFilters.offset), ...(state.candidateFilters.status ? { status: state.candidateFilters.status } : {}) })}`,
            )
          : { items: [], total: 0 };
      if (epoch !== state.epoch) return;
      state.data = {
        operations,
        leads: leadPage.items,
        leadPage,
        approvals,
        jobs,
        catalog,
        allCatalog,
        runs,
        leadDetail,
        candidates,
      };
      if (!state.dirty && !state.busy) {
        const scroll = window.scrollY;
        render();
        if (poll) window.scrollTo(0, scroll);
      }
      clearTimeout(state.timer);
      if (jobs.some((j) => ["PENDING", "RUNNING"].includes(j.status)))
        state.timer = setTimeout(() => {
          if (!state.dirty && !state.busy) load(true);
          else state.timer = setTimeout(() => load(true), 10000);
        }, 10000);
    } catch (error) {
      if (
        error.name !== "AbortError" &&
        epoch === state.epoch &&
        error.status !== 401
      ) {
        if (poll) {
          notice("Updates paused: " + error.message);
          state.timer = setTimeout(() => load(true), 10000);
        } else
          view.innerHTML = `<div class="error" role="alert">${esc(error.message)}</div><button data-reload>Try again</button>`;
      }
    }
  }
  function leadTable(leads) {
    const runs = state.data.operations.current_preparation || [];
    return leads.length
      ? `<div class="table-wrap"><table><thead><tr><th>Company</th><th>Preparation</th><th>Next action</th></tr></thead><tbody>${leads
          .map((l) => {
            const run =
              l.current_preparation || runs.find((r) => r.lead_id === l.id);
            return `<tr><td><a href="#lead/${esc(l.id)}" data-lead="${esc(l.id)}">${esc(l.company_name)}</a><br>${link(l.website, "Company website")}</td><td>${run ? badge(run.status) : "Not started"}${run?.stop_reason ? `<p class="muted">${esc(label(run.stop_reason))}</p>` : ""}</td><td><button data-lead="${esc(l.id)}">${run?.status === "NEEDS_REVIEW" ? "Review preparation" : "Open lead"}</button></td></tr>`;
          })
          .join("")}</tbody></table></div>`
      : empty(
          "No leads yet. Find companies or add a company to start preparation.",
        );
  }
  function candidateRow(c) {
    const reviewable = c.status === "READY_FOR_REVIEW" && canReviewCandidate();
    const retryable = !["ACCEPTED", "REJECTED", "KNOWN", "RETRY_PENDING"].includes(c.status) && canReviewCandidate();
    const tone = c.stale ? "attention" : c.status === "ACCEPTED" ? "success" : ["ASSESSMENT_FAILED", "FETCH_UNAVAILABLE"].includes(c.status) ? "attention" : "";
    return `<article class="discovery-row">
      <div class="discovery-row-main">
        <div class="discovery-company"><h3>${esc(c.company_name || c.domain)}</h3>${link(c.website || c.source_url, c.domain || "Company website")}</div>
        <div class="discovery-fit"><span class="discovery-cell-label">Customer fit</span><strong>${c.icp_code ? esc(productName(c.icp_code)) : "Not established"}</strong>${c.icp_code && c.confidence != null ? `<span class="muted">${esc(c.confidence)}% confidence</span>` : ""}${c.industry ? `<span class="muted">${esc(c.industry)}</span>` : ""}</div>
        <div class="discovery-status"><span class="discovery-cell-label">Status</span><span class="badge ${tone}">${esc(label(c.status))}</span>${c.stale ? badge("STALE") : ""}${c.failure_reason ? `<p class="discovery-issue">${esc(label(c.failure_reason))}. Retry available.</p>` : ""}${c.stale ? '<p class="discovery-issue">Targeting changed. Reassess before accepting.</p>' : ""}</div>
        <div class="discovery-row-actions">${reviewable ? command(`candidates/${c.id}/accept`, "Accept & start research", {note: ""}, c.stale || !state.data.operations.enabled) : ""}${retryable ? command(`candidates/${c.id}/retry`, "Reassess company", {}, !state.data.operations.enabled) : ""}${c.accepted_lead_id ? `<button data-lead="${esc(c.accepted_lead_id)}">Open accepted lead</button>` : ""}${!["ACCEPTED", "REJECTED"].includes(c.status) && !reviewable && !retryable ? '<span class="muted">Awaiting assessment</span>' : ""}</div>
      </div>
      <details class="discovery-row-details"><summary>Review details & evidence</summary><div class="discovery-detail-body">${c.reasoning ? `<p>${esc(c.reasoning)}</p>` : '<p class="muted">No assessment reasoning is available yet.</p>'}${c.evidence_quote ? evidence([{ source_url: c.source_url, evidence_quote: c.evidence_quote }]) : ""}${c.unknowns?.length ? `<p class="muted">Not established: ${esc(c.unknowns.join(" · "))}</p>` : ""}${c.review_note ? `<p><strong>Review note:</strong> ${esc(c.review_note)}</p>` : ""}${reviewable ? `<form data-command="candidates/${esc(c.id)}/reject">${field("note", "Reason for rejection", "", "required minlength=5 maxlength=1000")}<button>Reject candidate</button><div class="error" hidden role="alert"></div></form>` : ""}</div></details>
    </article>`;
  }
  function candidateInbox(page) {
    const first = page.total ? state.candidateFilters.offset + 1 : 0;
    return `<div class="discovery-toolbar"><form id="candidate-filters"><label for="candidate-status">Discovery status</label><div class="discovery-filter-controls"><select id="candidate-status" name="status">${[
      ["READY_FOR_REVIEW", "Awaiting your review"], ["", "All discoveries"], ["ACCEPTED", "Accepted"], ["REJECTED", "Rejected"],
    ].map(([s, t]) => `<option value="${s}" ${state.candidateFilters.status === s ? "selected" : ""}>${t}</option>`).join("")}</select><button>Apply filter</button></div></form><p class="muted">${page.total} ${page.total === 1 ? "discovery" : "discoveries"} in this view</p></div>
    ${page.items.length ? `<div class="discovery-list"><div class="discovery-list-heading" aria-hidden="true"><span>Company</span><span>Customer fit</span><span>Status</span><span>Actions</span></div>${page.items.map(candidateRow).join("")}</div>` : empty("No candidates in this view. Find leads to collect companies for review, or select All discoveries to inspect stopped assessments.")}
    <div class="discovery-pagination"><span class="muted">${first}–${Math.min(state.candidateFilters.offset + page.items.length, page.total)} of ${page.total}</span><div><button data-candidates-prev ${state.candidateFilters.offset ? "" : "disabled"}>Previous</button><button data-candidates-next ${state.candidateFilters.offset + 25 < page.total ? "" : "disabled"}>Next</button></div></div>`;
  }
  function render() {
    const d = state.data,
      view = document.querySelector("#view");
    if (!view) return;
    if (state.page === "overview") {
      const pending = d.approvals.filter(
          (a) => a.status === "PENDING" && !a.stale,
        ),
        stops = (d.operations.current_preparation || []).filter((r) =>
          ["FAILED", "NEEDS_REVIEW", "STALE", "CHANGES_REQUESTED"].includes(
            r.status,
          ),
        );
      view.innerHTML = `<div class="grid">${card("Ready for human review", `<h1>${pending.length}</h1><p>Pending drafts in the latest 100 approvals.</p><button data-page="approvals" class="primary">Review drafts</button>`)}${card("Preparation needs attention", `<h1>${stops.length}</h1><p>Current runs with a failure or review stop.</p><button data-page="leads">Review leads</button>`)}</div>${card("Your next step", !d.catalog.some((x) => x.kind === "PRODUCT") ? `<p>Add actual offerings and activate your product.</p>${isAdmin() ? '<button data-page="setup" class="primary">Set up product</button>' : "<p>Ask an administrator to configure this workspace.</p>"}` : !d.operations.enabled ? `<p>Automation is paused. An administrator can resume it from Product setup.</p>` : `<p>Automation is active. Find companies, prepare a lead, or review drafts.</p>${canWork() ? '<button data-page="discovery" class="primary">Find leads</button>' : ""}`)}${card("Workspace leads", leadTable(d.leads.slice(0, 5)))}`;
    } else if (state.page === "leads")
      view.innerHTML = card(
        "Companies",
        `<form id="lead-filters">${field("q", "Search companies", state.leadFilters.q, "maxlength=200", "search")}<label for="lead-status">Current preparation status</label><select name="status" id="lead-status"><option value="">All statuses</option>${["PREPARING", "NEEDS_REVIEW", "PENDING_APPROVAL", "APPROVED", "REJECTED", "CHANGES_REQUESTED", "FAILED", "STALE"].map((s) => `<option value="${s}" ${s === state.leadFilters.status ? "selected" : ""}>${esc(label(s))}</option>`).join("")}</select><div class="actions"><button class="primary">Apply filters</button><button type="button" data-page-reset>Refresh from first page</button></div></form><p class="muted">${esc(d.leadPage.total)} matching companies · Page ${state.leadFilters.previous.length + 1} · Newest first. Preparation states may change while browsing.</p><div id="lead-table">${leadTable(d.leads)}</div><div class="actions"><button type="button" data-page-prev ${state.leadFilters.previous.length ? "" : "disabled"}>Previous page</button><button type="button" data-page-next ${d.leadPage.next_cursor ? "" : "disabled"}>Next page</button></div>${canWork() ? `<details><summary>Add a company</summary><form data-command="leads">${field("company_name", "Company name", "", "required minlength=2 maxlength=200")}${field("website", "Official public website", "", "required maxlength=1500", "url")}<div class="error" hidden role="alert"></div><div class="actions"><button class="primary">Add company</button></div></form></details>` : ""}`,
      );
    else if (state.page === "discovery")
      view.innerHTML =
        card(
          "Find your next customers",
          `<p>Find companies matching your product and target customers. Review the evidence and accept suitable candidates before research starts. A batch may return fewer companies than its maximum.</p><p>Batch maximum: ${esc(d.operations.preferences?.batch_size ?? "Not configured")}</p>${canWork() ? command("discovery", "Find leads", {}, !d.operations.enabled) : empty("An administrator or operator can start discovery.")}${!d.operations.enabled ? '<p class="muted">Ask an administrator to activate or resume automation.</p>' : ""}`,
        ) +
        card("Candidate review", candidateInbox(d.candidates)) +
        card(
          "Discovery batches",
          jobCards(d.jobs.filter((j) => j.kind === "DISCOVERY")),
        ) +
        card("Accepted companies", leadTable(d.leads));
    else if (state.page === "setup") renderSetup();
    else if (state.page === "lead") renderLead();
    else if (state.page === "approvals")
      view.innerHTML = card(
        "Draft review",
        `<p>Decisions record human review. Approval does not send a message. Requested changes can be edited into a new version by an administrator or operator, then reviewed by another authorized person.</p>${d.approvals.length ? d.approvals.map((a) => approval(a)).join("") : empty("No drafts awaiting review yet.")}`,
      );
    else if (state.page === "operations")
      view.innerHTML =
        card(
          "Automation",
          `<p>${d.operations.enabled ? "Active" : "Paused"} · Next discovery: ${esc(d.operations.next_discovery_at || "Not scheduled")}</p><p>Stalled jobs: ${d.operations.stalled_jobs.length} · Delayed pending jobs: ${d.operations.delayed_pending_jobs.length}</p>`,
        ) +
        card("Jobs & history", jobCards(d.jobs)) +
        card(
          "Providers: last observed requests",
          Object.entries(d.operations.provider_health || {})
            .map(
              ([name, value]) =>
                `<p>${esc(name)} · ${esc(label(value.last_request_status))} · ${esc(value.at)}</p>`,
            )
            .join("") || empty("No provider requests observed."),
        ) +
        card(
          "Recent reservations",
          `<p>Latest ${d.operations.recent_provider_usage.length} records, up to 100. Conservative USD reservations, not invoices or remaining budget.</p>${d.operations.recent_provider_usage.map((u) => `<p>${esc(u.provider)} / ${esc(u.operation)} · ${badge(u.status)} · $${(Number(u.estimated_microusd || 0) / 1000000).toFixed(6)}<details><summary>Reported usage</summary><pre>${esc(JSON.stringify(u.usage, null, 2))}</pre></details></p>`).join("")}`,
        );
    const filters = document.querySelector("#lead-filters");
    if (filters)
      filters.onsubmit = async (e) => {
        e.preventDefault();
        if (state.busy) return;
        if (
          document.querySelector("form[data-command][data-dirty]") &&
          !confirm("Discard the unsaved company form and apply filters?")
        )
          return;
        const values = Object.fromEntries(new FormData(filters));
        resetRequests();
        state.dirty = false;
        state.leadFilters = {
          q: values.q.trim(),
          status: values.status,
          cursor: null,
          previous: [],
        };
        await load();
      };
  }
  function command(path, title, payload = {}, disabled = false) {
    return `<form data-command="${esc(path)}" data-payload="${esc(JSON.stringify(payload))}"><div class="error" hidden role="alert"></div><div class="actions"><button class="primary" ${disabled ? "disabled" : ""}>${esc(title)}</button></div></form>`;
  }
  function jobCards(jobs) {
    return jobs.length
      ? jobs
          .map(
            (j) =>
              `<article class="card"><strong>${esc(label(j.kind))}</strong> ${badge(j.status)}<p class="muted">Attempt ${esc(j.attempts)} of ${esc(j.max_attempts)} · ${esc(j.created_at)}</p>${j.kind === "DISCOVERY" && j.result?.counts ? `<p>Searches: ${esc(j.result.counts.searches_attempted)} · Websites: ${esc(j.result.counts.websites_attempted)} · Pages: ${esc(j.result.counts.pages_attempted)} · Assessments: ${esc(j.result.counts.assessments_attempted)} · Candidates: ${esc(j.result.counts.candidates_ready)}</p><p>${esc(label(j.result.outcome))}. Suitable candidates await your acceptance.</p>` : ""}${j.failure_code ? `<p>${esc(label(j.failure_code))}. ${/PROVIDER|BUDGET|CONFIG|MODEL/.test(j.failure_code) ? "Ask an administrator to review configuration." : "Review the saved context before retrying."}</p>` : ""}<details><summary>Stage events & technical details</summary><pre>${esc(JSON.stringify({ history: j.history, result: j.result, available_at: j.available_at, lease_until: j.lease_until }, null, 2))}</pre></details>${canWork() && j.status === "FAILED" ? command(`jobs/${j.id}/retry`, "Retry failed job") : ""}</article>`,
          )
          .join("")
      : empty("No jobs recorded yet.");
  }
  function researchFacts(facts) {
    return [...new Set(facts.map((f) => f.category))]
      .map(
        (category) =>
          `<section><h3>${esc(label(category))}</h3>${facts
            .filter((f) => f.category === category)
            .map(
              (f) =>
                `<article><small>${esc(label(f.kind))} · Confidence ${esc(f.confidence)}/100</small><p>${esc(f.statement)}</p>${evidence([f])}</article>`,
            )
            .join("")}</section>`,
      )
      .join("");
  }
  function draft(value, catalog = state.data.catalog) {
    const name =
      catalog?.find((p) => p.code === value.product_code)?.name ||
      value.product_code ||
      "Not selected";
    return `<p>${esc(label(value.channel))} · ${esc(value.recipient || "Recipient unavailable")} · ${esc(name)}</p><h3>${esc(value.subject)}</h3><div class="draft">${esc(value.body)}</div>${evidence(value.evidence)}`;
  }
  function approval(a) {
    const snapshot = a.snapshot || {},
      value = snapshot.draft || snapshot.DRAFTING || snapshot,
      ctx = snapshot.results || {},
      company = snapshot.inputs?.company || {},
      person = ctx.CONTACT_SEARCH?.selected_contact,
      score = ctx.SCORING,
      selfEdited =
        !!snapshot.revision?.editor_id &&
        snapshot.revision.editor_id === state.user?.id;
    const version = a.version || snapshot.revision?.version || 1;
    let controls = a.decision?.note
      ? `<p><strong>Reviewer note:</strong> ${esc(a.decision.note)}</p>`
      : "";
    if (canReview() && a.status === "PENDING")
      controls += `<form data-command="approvals/${esc(a.id)}/decision">${area("note", "Review note (required for every decision)", "", "required minlength=5 maxlength=1000")}<div class="error" hidden role="alert"></div>${selfEdited ? '<p class="muted">You edited this version. Another authorized reviewer must approve it.</p>' : ""}<div class="actions"><button name="decision" value="APPROVED" class="primary" ${a.stale || selfEdited ? "disabled" : ""}>Approve draft</button><button name="decision" value="CHANGES_REQUESTED">Request changes</button><button name="decision" value="REJECTED">Reject</button></div></form>`;
    if (canWork() && a.status === "CHANGES_REQUESTED" && !a.stale)
      controls += `<details><summary>Edit requested changes</summary><p>Creates a new immutable version. Channel, recipient and offering stay fixed. Another authorized person must approve your revision.</p><form data-command="approvals/${esc(a.id)}/revision" data-revision data-version="${version}">${field("subject", "Revised subject", value.subject, "required minlength=3 maxlength=200")}${area("body", "Revised message", value.body, "required minlength=30 maxlength=3000")}<h3>Supporting evidence</h3><p class="muted">Keep exact quotes from the saved official research. Citation validity does not verify every sentence.</p>${(value.evidence || []).map((ev, i) => `<fieldset><legend>Citation ${i + 1}</legend>${field(`source_${i}`, "Saved source URL", ev.source_url, "required maxlength=1500", "url")}${area(`quote_${i}`, "Exact saved evidence quote", ev.evidence_quote, "required minlength=8 maxlength=500")}</fieldset>`).join("")}${area("note", "Revision note", "", "required minlength=5 maxlength=1000")}<div class="error" hidden role="alert"></div><div class="actions"><button class="primary">Submit revision for review</button></div></form></details>`;
    return `<article class="card">${badge(a.status)} ${a.stale ? badge("STALE") : ""}<p class="muted">Version ${version} · Saved ${esc(a.created_at)}</p><h3>${esc(company.company_name || company.name || "Saved company context")}</h3>${person ? `<p>${esc(person.name)} · ${esc(person.role)}</p>` : ""}${score ? `<p>Saved qualification: ${esc(score.score)}/100 · Selected offering: ${esc(snapshot.inputs?.catalog?.find((p) => p.code === value.product_code)?.name || value.product_code)}</p>` : ""}${draft(value, snapshot.inputs?.catalog || [])}<details><summary>Saved supporting research</summary>${(ctx.RESEARCH?.facts || []).map((f) => `<p>${esc(f.statement)}</p>${evidence([f])}`).join("") || empty("No research included in this snapshot.")}</details>${snapshot.revision ? `<p>Revision note: ${esc(snapshot.revision.note)}<br>Original reviewer note: ${esc(snapshot.revision.reviewer_note)}</p>` : ""}${a.stale ? '<p class="error">This draft is stale. Prepare and review a fresh draft before approving.</p>' : ""}${controls}</article>`;
  }
  function renderLead() {
    const d = state.data,
      l = d.leadDetail,
      run = d.runs.find((r) => r.current) || d.runs[0],
      results = run?.results || {},
      contact = l?.primary_contact || results.CONTACT_SEARCH?.selected_contact;
    if (!l) {
      document.querySelector("#view").innerHTML = empty(
        "This lead is unavailable in the current workspace.",
      );
      return;
    }
    const tabs = [
      "Overview",
      "Research",
      "People",
      "Qualification",
      "Outreach",
      "Activity",
    ];
    let html = `<button data-page="leads">← Back to leads</button><div class="grid">${card(l.company_name, `${link(l.website, "Official website")}<p>${run ? badge(run.status) : "Preparation not started"}</p>`)}${card("Primary contact", contact ? `<strong>${esc(contact.name)}</strong><p>${esc(contact.role)}<br>${esc(contact.email || "No supported email")}</p>` : empty("No supported primary contact selected yet."))}</div><div class="tabs" role="tablist" aria-label="Lead sections">${tabs.map((t, i) => `<button id="tab-${i}" role="tab" aria-controls="lead-panel" aria-selected="${t === state.tab}" tabindex="${t === state.tab ? 0 : -1}" data-tab="${t}">${t}</button>`).join("")}</div><section id="lead-panel" role="tabpanel" aria-labelledby="tab-${tabs.indexOf(state.tab)}">`;
    if (state.tab === "Overview")
      html += card(
        "Preparation",
        `<p>${run?.stop_reason ? esc(label(run.stop_reason)) : "Prepare this lead to collect evidence, qualify fit, and create a draft for review."}</p>${canWork() ? command(`leads/${l.id}/prepare`, "Start fresh preparation", {}, !d.operations.enabled) : ""}${!d.operations.enabled ? "<p>Automation is paused. Ask an administrator to resume it.</p>" : ""}<p class="muted">Stage results arrive progressively. Partial evidence remains available if work stops.</p>`,
      );
    if (state.tab === "Research") {
      const r = results.RESEARCH;
      html += r
        ? card(
            "Company brief",
            `<p>Industry: ${esc(r.industry?.name || r.industry?.statement || (typeof r.industry === "string" ? r.industry : "Not established from available sources"))}</p><div class="facts">${researchFacts(r.facts || [])}</div><h3>Unknowns & coverage</h3>${(r.unknowns || []).map((x) => `<p>${esc(x)}</p>`).join("")}${r.coverage ? `<details><summary>Coverage details</summary><pre>${esc(JSON.stringify(r.coverage, null, 2))}</pre></details>` : ""}`,
          )
        : card("Research", empty("Research has not completed yet."));
    }
    if (state.tab === "People") {
      const r = results.CONTACT_SEARCH,
        stop =
          run?.status === "NEEDS_REVIEW" &&
          ["SUPPORTED_CONTACT_REQUIRED", "CONTACT_SEARCH_UNAVAILABLE"].includes(
            run.stop_reason,
          );
      html += card(
        "People & public contacts",
        `<p class="muted">Public name/company matches do not establish current employment. Review the saved evidence.</p>${r ? (r.people || []).map((p, i) => `<article class="card"><strong>${esc(p.name)}</strong><p>${esc(p.role)} · ${esc(p.email || "No supported email")}</p>${evidence([p])}${[...(p.profiles || []), ...(p.profile_candidates || [])].map((v) => `<p>${link(v.url, "Professional profile")} · ${esc(v.confidence ?? "Review required")}${stop && canWork() && v.platform === "linkedin.com" ? command(`preparation/${run.id}/contact`, "Choose supported profile", { person_index: i, profile_url: v.url }, !d.operations.enabled) : ""}</p>`).join("")}${stop && canWork() && p.email ? command(`preparation/${run.id}/contact`, "Choose this contact", { person_index: i }, !d.operations.enabled) : ""}</article>`).join("") || empty("No named people found.") : empty("Contact search has not completed yet.")}${r?.unavailable_queries ? `<p class="muted">${esc(r.unavailable_queries)} contact searches were unavailable. Retry search or review supported contacts.</p>` : ""}`,
      );
      if (stop && canWork())
        html += card(
          "Resolve contact review",
          `${command(`preparation/${run.id}/retry-contact-search`, "Retry profile search", {}, !d.operations.enabled)}<details><summary>Enter a source-backed business contact</summary><p>Use an exact quote from an official company page already saved in Research. It must support the name, role and email.</p><form data-command="preparation/${run.id}/contact" data-contact>${field("name", "Name", "", "required minlength=3 maxlength=150")}${field("role", "Role", "", "required minlength=2 maxlength=200")}${field("email", "Business email", "", "required maxlength=254", "email")}${field("phone", "Phone (optional)", "", "maxlength=80")}${field("source_url", "Saved official source URL", "", "required maxlength=1500", "url")}${area("evidence_quote", "Exact saved quote", "", "required minlength=8 maxlength=500")}<div class="error" hidden role="alert"></div><div class="actions"><button class="primary" ${!d.operations.enabled ? "disabled" : ""}>Continue with contact</button></div></form></details>`,
        );
    }
    if (state.tab === "Qualification") {
      const s = results.SCORING,
        m = results.MATCHING;
      html +=
        card(
          "Qualification",
          s
            ? `<h3>Score ${esc(s.score)}/100</h3><p>Relevance ${esc(s.relevance)} · Opportunity ${esc(s.opportunity)} (components of total; not purchase probability)</p>${(s.criteria || []).map((c) => `<article><h3>${esc(c.criterion)} · ${esc(c.points)} points</h3><p>${esc(c.rationale)}</p>${evidence(c.evidence)}</article>`).join("")}<p>${esc(label(s.stop_reason || "Scoring complete"))}</p>${(s.unknowns || []).map((x) => `<p>${esc(x)}</p>`).join("")}<details><summary>Scoring adjustments</summary><pre>${esc(JSON.stringify(s.adjustments || [], null, 2))}</pre></details>`
            : empty("Qualification has not completed yet."),
        ) +
        card(
          "Product fit",
          m
            ? `<p>Selected: ${esc(productName(m.selected_product))}</p>${(m.matches || []).map((p) => `<h3>${esc(productName(p.product_code))} · Fit ${esc(p.fit)}/100</h3><p>${esc(p.rationale)}</p>${evidence(p.evidence)}`).join("")}<p>${esc(m.stop_reason ? label(m.stop_reason) : "")}</p><p class="muted">Low qualification or unsupported matches cannot be manually overridden.</p>`
            : empty("Product matching has not completed yet."),
        );
    }
    if (state.tab === "Outreach") {
      const a = d.approvals.find((a) => a.run_id === run?.id);
      html += a
        ? approval(a)
        : card(
            "Outreach draft",
            results.DRAFTING
              ? draft(results.DRAFTING)
              : empty(
                  "A draft will appear after evidence, contact and product-fit checks complete.",
                ),
          );
    }
    if (state.tab === "Activity")
      html +=
        card(
          "Preparation history",
          d.runs
            .map(
              (r) =>
                `<p>${badge(r.status)} ${r.current ? "Current" : "Historical"} · ${esc(r.created_at)} · ${esc(label(r.stop_reason || "No stop reason"))}</p>`,
            )
            .join("") || empty("No preparation history."),
        ) +
        card("Linked jobs", jobCards(d.jobs.filter((j) => j.lead_id === l.id)));
    document.querySelector("#view").innerHTML = html + "</section>";
    document.querySelector(".tabs").onkeydown = (e) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
      e.preventDefault();
      let i = tabs.indexOf(state.tab);
      i =
        e.key === "Home"
          ? 0
          : e.key === "End"
            ? tabs.length - 1
            : (i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) %
              tabs.length;
      state.tab = tabs[i];
      renderLead();
      document.querySelector(`[data-tab="${state.tab}"]`).focus();
    };
  }
  function renderSetup() {
    const d = state.data;
    if (!isAdmin()) {
      document.querySelector("#view").innerHTML = empty(
        "Only administrators can configure a product.",
      );
      return;
    }
    if (!state.setup)
      state.setup = {
        step: 0,
        values: { ...d.operations.preferences },
        items: d.catalog
          .filter((c) => c.kind === "PRODUCT")
          .map((c) => ({ ...c })),
        key: uid(),
        saved: [],
      };
    const s = state.setup,
      v = s.values;
    let body = `<ol class="stepper">${["1. Product details", "2. Actual offerings", "3. Review & activate"].map((x, i) => `<li class="${i === s.step ? "active" : ""}" ${i === s.step ? 'aria-current="step"' : ""}>${x}</li>`).join("")}</ol><form id="setup-form"><div class="error" hidden role="alert"></div>`;
    if (s.step === 0)
      body +=
        area(
          "product_description",
          "Describe the real product",
          v.product_description,
          "required minlength=20 maxlength=5000",
        ) +
        area(
          "target_customers",
          "Target customers (optional)",
          v.target_customers,
          "maxlength=2000",
        ) +
        `<div class="grid">${field("country", "Country code", v.country || "MY", 'required pattern="[A-Z]{2}" maxlength=2')}${field("language", "Language", v.language || "English", "required minlength=2 maxlength=80")}</div>` +
        field(
          "brand_voice",
          "Brand voice",
          v.brand_voice || "Professional and concise",
          "maxlength=500",
        ) +
        field(
          "batch_size",
          "Maximum companies per batch",
          v.batch_size || 3,
          "required min=1 max=10 step=1",
          "number",
        );
    if (s.step === 1) {
      body += `<p>Save the actual offerings you sell. These are used for matching and draft claims.</p><div id="offerings">${s.items.map((p, i) => offering(p, i)).join("")}</div><button type="button" id="add-offering">Add offering</button><h3>Existing targeting profiles</h3>${
        d.catalog
          .filter((p) => p.kind === "ICP")
          .map((p) => `<p>${esc(p.name)} · ${esc(p.description)}</p>`)
          .join("") ||
        empty("Targeting profiles will be generated during activation.")
      }`;
    }
    if (s.step === 2)
      body += `<h3>Product description</h3><p>${esc(v.product_description)}</p><p>${esc(v.target_customers || "Targeting will be generated from the product.")}</p><p>${esc(v.country)} · ${esc(v.language)} · Batch maximum ${esc(v.batch_size)}</p><h3>Offerings</h3>${s.items.map((p) => `<p><strong>${esc(p.name)}</strong> (${esc(p.code)})<br>${esc(p.description)}</p>`).join("")}<p class="muted">Offerings save individually before activation. If activation fails, saved offerings remain and you can retry.</p>${s.saved.length ? `<p class="success-note">Saved offerings: ${esc(s.saved.join(", "))}</p>` : ""}`;
    body += `<div class="actions">${s.step ? '<button type="button" id="setup-back">Back</button>' : ""}<button class="primary">${s.step === 2 ? "Save offerings & activate" : "Continue"}</button></div></form>`;
    document.querySelector("#view").innerHTML =
      `<div class="setup">${card("Product setup", body)}${card("Automation controls", `<p>${d.operations.enabled ? "Active" : "Paused"}</p>${command(`automation/${d.operations.enabled ? "pause" : "resume"}`, d.operations.enabled ? "Pause automation" : "Resume automation")}<p class="muted">Resuming does not retry failed jobs automatically.</p>`)}${catalogLifecycle()}${card("Setup activity", jobCards(d.jobs.filter((j) => j.kind === "SETUP")))}</div>`;
    document.querySelector("#setup-back")?.addEventListener("click", () => {
      captureSetup();
      s.step--;
      renderSetup();
    });
    document.querySelector("#add-offering")?.addEventListener("click", () => {
      captureSetup();
      s.items.push({
        code: "",
        name: "",
        description: "",
        kind: "PRODUCT",
        rules: {},
      });
      state.dirty = true;
      renderSetup();
    });
    document.querySelector("#setup-form").onsubmit = async (e) => {
      e.preventDefault();
      captureSetup();
      if (
        s.step === 1 &&
        (!s.items.length ||
          new Set(s.items.map((x) => x.code)).size !== s.items.length)
      ) {
        formError(e.target, "Add at least one offering with a unique code.");
        return;
      }
      if (s.step < 2) {
        s.step++;
        renderSetup();
        return;
      }
      const form = e.target;
      state.busy = true;
      form.querySelectorAll("button").forEach((x) => (x.disabled = true));
      try {
        for (const item of s.items) {
          await request("catalog", "PUT", {
            kind: "PRODUCT",
            code: item.code,
            name: item.name,
            description: item.description,
            rules: item.rules || {},
          });
          if (!s.saved.includes(item.code)) s.saved.push(item.code);
        }
        await request("automation/activate", "POST", {
          ...s.values,
          idempotency_key: s.key,
        });
        state.dirty = false;
        state.setup = null;
        notice(
          "Product setup queued. Follow progress in Activity & operations.",
        );
        state.busy = false;
        await navigate("operations");
      } catch (error) {
        if (error.name !== "AbortError")
          formError(
            form,
            `${error.message}${s.saved.length ? " Saved offerings remain: " + s.saved.join(", ") + ". Retry with the same request." : ""}`,
          );
        state.busy = false;
        form.querySelectorAll("button").forEach((x) => (x.disabled = false));
      }
    };
  }
  function offering(p, i) {
    return `<fieldset class="card"><legend>Offering ${i + 1}</legend>${field(`code_${i}`, "Stable catalog code", p.code, 'required pattern="[A-Z0-9_]+" maxlength=80')}${field(`name_${i}`, "Offering name", p.name, "required minlength=2 maxlength=120")}${area(`description_${i}`, "Documented capabilities", p.description, "required minlength=10 maxlength=5000")}</fieldset>`;
  }
  function catalogLifecycle() {
    const d = state.data,
      blocked =
        d.operations.enabled &&
        d.jobs.some(
          (j) => j.managed && ["PENDING", "RUNNING"].includes(j.status),
        );
    return card(
      "Catalog lifecycle",
      `<p>Deactivation retains historical evidence and invalidates older draft contexts. Removing the last active offering or targeting profile pauses automation. Reactivation requires an explicit resume.</p>${blocked ? '<p class="muted">Pause automation before changing catalog items while managed work is active.</p>' : ""}${d.allCatalog.map((c) => `<article class="card"><strong>${esc(c.name)}</strong> ${badge(c.active ? "ACTIVE" : "INACTIVE")}<p class="muted">${esc(c.kind)} · ${esc(c.code)} · Version ${esc(c.version)}</p><form data-command="catalog/${esc(c.id)}" data-method="PATCH" data-payload="${esc(JSON.stringify({ active: !c.active }))}"><div class="error" hidden role="alert"></div><div class="actions"><button ${blocked ? "disabled" : ""}>${c.active ? "Deactivate" : "Reactivate"} ${esc(c.name)}</button></div></form></article>`).join("") || empty("No catalog items configured.")}`,
    );
  }
  function captureSetup() {
    const s = state.setup,
      form = document.querySelector("#setup-form"),
      data = Object.fromEntries(new FormData(form)),
      before = JSON.stringify([s.values, s.items]);
    if (s.step === 0)
      s.values = {
        product_description: data.product_description,
        target_customers: data.target_customers,
        country: data.country,
        language: data.language,
        brand_voice: data.brand_voice,
        batch_size: Number(data.batch_size),
      };
    if (s.step === 1)
      s.items = s.items.map((p, i) => ({
        ...p,
        code: data[`code_${i}`],
        name: data[`name_${i}`],
        description: data[`description_${i}`],
      }));
    if (before !== JSON.stringify([s.values, s.items])) {
      s.key = uid();
      s.saved = [];
    }
  }
  function formError(form, text) {
    const node = form.querySelector(".error");
    node.hidden = false;
    node.textContent = text;
    node.scrollIntoView({ block: "nearest" });
  }
  document.addEventListener("input", (e) => {
    if (e.target.closest("form") && !e.target.closest("#login-form")) {
      state.dirty = true;
      e.target.closest("form").dataset.dirty = "1";
    }
  });
  document.addEventListener("submit", async (e) => {
    const form = e.target;
    if (form.id === "candidate-filters") {
      e.preventDefault();
      state.candidateFilters = {
        status: new FormData(form).get("status"),
        offset: 0,
      };
      state.dirty = false;
      await load();
      return;
    }
    if (!form.matches("[data-command]")) return;
    e.preventDefault();
    if (state.busy) return;
    state.busy = true;
    let payload = {
      ...JSON.parse(form.dataset.payload || "{}"),
      ...Object.fromEntries(new FormData(form)),
    };
    if (e.submitter?.name) payload[e.submitter.name] = e.submitter.value;
    if (form.hasAttribute("data-contact")) {
      if (!payload.phone) delete payload.phone;
      payload = { business_contact: payload };
    }
    if (form.hasAttribute("data-revision")) {
      const values = payload,
        evidence = [];
      for (let i = 0; values[`source_${i}`] !== undefined; i++)
        evidence.push({
          source_url: values[`source_${i}`],
          evidence_quote: values[`quote_${i}`],
        });
      payload = {
        subject: values.subject,
        body: values.body,
        note: values.note,
        evidence,
        expected_version: Number(form.dataset.version),
      };
      const fingerprint = JSON.stringify(payload);
      if (form.dataset.keyPayload !== fingerprint) {
        form.dataset.key = uid();
        form.dataset.keyPayload = fingerprint;
      }
      payload.idempotency_key = form.dataset.key;
    }
    if (/^(discovery|leads\/.+\/prepare)$/.test(form.dataset.command)) {
      form.dataset.key ||= uid();
      payload.idempotency_key = form.dataset.key;
    }
    const buttons = [...form.querySelectorAll("button")],
      disabled = buttons.map((b) => b.disabled);
    buttons.forEach((b) => (b.disabled = true));
    try {
      await request(
        form.dataset.command,
        form.dataset.method || "POST",
        Object.keys(payload).length ? payload : undefined,
      );
      state.dirty = false;
      notice(
        form.dataset.command.includes("decision")
          ? "Decision saved. No message was sent."
          : form.dataset.command.startsWith("candidates/") && form.dataset.command.endsWith("/accept")
            ? "Candidate accepted. Research has been queued."
            : form.dataset.command.startsWith("candidates/") && form.dataset.command.endsWith("/reject")
              ? "Candidate rejected. Your decision has been saved."
              : form.dataset.command.startsWith("candidates/") && form.dataset.command.endsWith("/retry")
                ? "Company reassessment queued."
                : "Request accepted. Check the current status below.",
      );
      state.busy = false;
      await load();
    } catch (error) {
      if (error.name !== "AbortError" && error.status !== 401)
        formError(form, error.message);
      state.busy = false;
      buttons.forEach((b, i) => (b.disabled = disabled[i]));
    }
  });
  document.addEventListener("click", async (e) => {
    const button = e.target.closest(
      "[data-candidates-prev],[data-candidates-next]",
    );
    if (!button || button.disabled) return;
    state.candidateFilters.offset = Math.max(
      0,
      state.candidateFilters.offset +
        (button.hasAttribute("data-candidates-next") ? 25 : -25),
    );
    state.dirty = false;
    await load();
  });
  document.addEventListener("click", (e) => {
    const theme = e.target.closest("button[data-theme]");
    if (theme) {
      const values = ["system", "light", "dark"],
        next =
          values[
            (values.indexOf(
              localStorage.getItem("marketing-theme") || "system",
            ) +
              1) %
              3
          ];
      window.marketingTheme(next);
      theme.textContent = "Theme: " + next;
    }
    const page = e.target.closest("[data-page]"),
      lead = e.target.closest("[data-lead]"),
      tab = e.target.closest("[data-tab]");
    if (page) {
      e.preventDefault();
      navigate(page.dataset.page);
    }
    if (lead) {
      e.preventDefault();
      navigate("lead", lead.dataset.lead);
    }
    if (tab) {
      if (state.dirty && !confirm("Leave your unsaved changes?")) return;
      state.dirty = false;
      state.tab = tab.dataset.tab;
      renderLead();
    }
    if (e.target.closest("[data-reload]")) load();
    const paging = e.target.closest(
      "[data-page-prev],[data-page-next],[data-page-reset]",
    );
    if (paging && !state.busy) {
      if (state.dirty && !confirm("Leave your unsaved changes?")) return;
      resetRequests();
      state.dirty = false;
      if (paging.hasAttribute("data-page-next")) {
        state.leadFilters.previous.push(state.leadFilters.cursor);
        state.leadFilters.cursor = state.data.leadPage.next_cursor;
      } else if (paging.hasAttribute("data-page-prev"))
        state.leadFilters.cursor = state.leadFilters.previous.pop() || null;
      else {
        state.leadFilters.cursor = null;
        state.leadFilters.previous = [];
      }
      load();
    }
  });
  window.addEventListener("beforeunload", (e) => {
    if (state.dirty || state.busy) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearTimeout(state.timer);
    else if (state.workspace && !state.dirty && !state.busy) load(true);
  });
  boot();
})();
