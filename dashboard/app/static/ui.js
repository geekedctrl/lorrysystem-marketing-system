document.addEventListener("DOMContentLoaded", () => {
  const header = document.querySelector(".topbar");
  if (header)
    new ResizeObserver(() =>
      document.documentElement.style.setProperty(
        "--header-height",
        header.getBoundingClientRect().height + "px",
      ),
    ).observe(header);
  const body = document.body,
    sidebar = document.querySelector(".sidebar"),
    mobile = document.querySelector(".mobile-nav"),
    scrim = document.querySelector(".sidebar-scrim");
  function drawer(open) {
    body.classList.toggle("nav-open", open);
    mobile?.setAttribute("aria-expanded", String(open));
    if (scrim) scrim.hidden = !open;
    if (sidebar)
      sidebar.inert = matchMedia("(max-width:760px)").matches && !open;
    if (open) sidebar?.querySelector("a")?.focus();
    else mobile?.focus();
  }
  const mobileMedia = matchMedia("(max-width:760px)");
  const syncInert = () => {
    if (sidebar)
      sidebar.inert =
        mobileMedia.matches && !body.classList.contains("nav-open");
  };
  mobileMedia.addEventListener("change", () => {
    syncInert();
    if (!mobileMedia.matches) {
      body.classList.remove("nav-open");
      if (scrim) scrim.hidden = true;
    }
  });
  syncInert();
  document.addEventListener("keydown", (e) => {
    if (
      e.key === "Tab" &&
      mobileMedia.matches &&
      body.classList.contains("nav-open")
    ) {
      const elements = [...sidebar.querySelectorAll("a,button,select")].filter(
        (x) => x.offsetParent !== null,
      );
      const first = elements[0],
        last = elements[elements.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  });
  mobile?.addEventListener("click", () =>
    drawer(!body.classList.contains("nav-open")),
  );
  scrim?.addEventListener("click", () => drawer(false));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && body.classList.contains("nav-open"))
      drawer(false);
  });
  const collapse = document.querySelector(".nav-collapse");
  try {
    body.classList.toggle(
      "nav-collapsed",
      localStorage.getItem("marketing-nav") === "collapsed",
    );
  } catch (_) {}
  collapse?.setAttribute(
    "aria-expanded",
    String(!body.classList.contains("nav-collapsed")),
  );
  collapse?.addEventListener("click", () => {
    body.classList.toggle("nav-collapsed");
    collapse.setAttribute(
      "aria-expanded",
      String(!body.classList.contains("nav-collapsed")),
    );
    collapse.setAttribute(
      "aria-label",
      body.classList.contains("nav-collapsed")
        ? "Expand sidebar"
        : "Collapse sidebar",
    );
    try {
      localStorage.setItem(
        "marketing-nav",
        body.classList.contains("nav-collapsed") ? "collapsed" : "expanded",
      );
    } catch (_) {}
  });
  document.querySelectorAll(".theme-toggle").forEach((button) => {
    const label = () => {
      button.title =
        "Theme: " +
        document.documentElement.dataset.themeChoice +
        " (click to change)";
      button.setAttribute("aria-label", button.title);
    };
    label();
    button.addEventListener("click", () => {
      const choices = ["system", "light", "dark"];
      window.marketingTheme(
        choices[
          (choices.indexOf(document.documentElement.dataset.themeChoice) + 1) %
            3
        ],
      );
      label();
    });
  });
  document.querySelectorAll("[data-tabs]").forEach((group) => {
    const buttons = [...group.querySelectorAll('[role="tab"]')],
      panels = [
        ...document.querySelectorAll(
          '[data-tab-panel="' + group.dataset.tabs + '"]',
        ),
      ];
    const activate = (id) => {
      buttons.forEach((b) => {
        const selected = b.getAttribute("aria-controls") === id;
        b.setAttribute("aria-selected", String(selected));
        b.tabIndex = selected ? 0 : -1;
      });
      panels.forEach((p) => (p.hidden = p.id !== id));
      try {
        sessionStorage.setItem(
          "marketing-tab:" + location.pathname + ":" + group.dataset.tabs,
          id,
        );
      } catch (_) {}
    };
    buttons.forEach((b, i) => {
      b.addEventListener("click", () =>
        activate(b.getAttribute("aria-controls")),
      );
      b.addEventListener("keydown", (e) => {
        let index;
        if (e.key === "ArrowRight") index = (i + 1) % buttons.length;
        if (e.key === "ArrowLeft")
          index = (i + buttons.length - 1) % buttons.length;
        if (e.key === "Home") index = 0;
        if (e.key === "End") index = buttons.length - 1;
        if (index !== undefined) {
          e.preventDefault();
          buttons[index].click();
          buttons[index].focus();
        }
      });
    });
    let saved;
    try {
      saved = sessionStorage.getItem(
        "marketing-tab:" + location.pathname + ":" + group.dataset.tabs,
      );
    } catch (_) {}
    activate(
      buttons.some((b) => b.getAttribute("aria-controls") === saved)
        ? saved
        : buttons[0]?.getAttribute("aria-controls"),
    );
    const reveal = () => {
      if (!location.hash) return;
      let target = document.getElementById(
        decodeURIComponent(location.hash.slice(1)),
      );
      const panel = target?.closest("[data-tab-panel]");
      if (panel && panel.dataset.tabPanel === group.dataset.tabs) {
        activate(panel.id);
        target.scrollIntoView({ block: "start" });
      }
    };
    window.addEventListener("hashchange", reveal);
    reveal();
  });
  document.querySelectorAll('a[data-parent="leads"]').forEach((a) => {
    try {
      a.href = sessionStorage.getItem("marketing-lead-list") || "/leads";
    } catch (_) {}
  });
  if (location.pathname === "/leads")
    try {
      sessionStorage.setItem(
        "marketing-lead-list",
        location.pathname + location.search,
      );
    } catch (_) {}
  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("input", () => {
      form.dataset.dirty = "true";
    });
    form.addEventListener("submit", (e) => {
      if (e.defaultPrevented) return;
      if (form.dataset.submitting === "true") {
        e.preventDefault();
        return;
      }
      form.dataset.submitting = "true";
      form.setAttribute("aria-busy", "true");
      setTimeout(() => {
        form.dataset.submitting = "";
        form.removeAttribute("aria-busy");
      }, 10000);
    });
  });
  const wizard = document.querySelector("[data-wizard]");
  if (wizard) {
    const steps = [...wizard.querySelectorAll("[data-step]")],
      indicators = [...wizard.querySelectorAll(".setup-step")];
    let index = 0;
    const show = () => {
      steps.forEach((s, i) => (s.hidden = i !== index));
      indicators.forEach((s, i) => {
        s.setAttribute("aria-current", i === index ? "step" : "false");
      });
      wizard.querySelector("[data-previous]").hidden = index === 0;
      wizard.querySelector("[data-next]").hidden = index === steps.length - 1;
      wizard.querySelector("[data-activate]").hidden =
        index !== steps.length - 1;
      wizard.querySelector("[data-activate]").disabled =
        index !== steps.length - 1;
      wizard.querySelector("[data-step-count]").textContent =
        "Step " + (index + 1) + " of " + steps.length;
      if (index === 2) {
        const review = wizard.querySelector("[data-setup-review]");
        review.replaceChildren();
        ["product_type", "description", "country_code", "language"].forEach(
          (name) => {
            const field = wizard.elements[name],
              p = document.createElement("p");
            p.textContent =
              (field.labels?.[0]?.childNodes[0]?.textContent || name) +
              ": " +
              (field.tagName === "SELECT"
                ? field.selectedOptions[0].textContent
                : field.value);
            review.append(p);
          },
        );
        const p = document.createElement("p");
        p.textContent =
          "Catalog: " +
          [...wizard.querySelectorAll('[name="offering_name"]')]
            .map((x) => x.value)
            .join(", ");
        review.append(p);
      }
    };
    wizard.querySelector("[data-next]").addEventListener("click", () => {
      const invalid = [
        ...steps[index].querySelectorAll("input,select,textarea"),
      ].find((f) => !f.checkValidity());
      if (invalid) {
        invalid.reportValidity();
        return;
      }
      if (index === 1 && !wizard.querySelector('[name="offering_name"]')) {
        wizard.querySelector("#add-offering").click();
        return;
      }
      index++;
      show();
    });
    wizard.querySelector("[data-previous]").addEventListener("click", () => {
      index--;
      show();
    });
    wizard.addEventListener("submit", (e) => {
      if (index !== steps.length - 1) {
        e.preventDefault();
        wizard.dataset.submitting = "";
        wizard.querySelector("[data-next]").click();
      }
    });
    wizard.addEventListener(
      "invalid",
      (e) => {
        const step = e.target.closest("[data-step]");
        if (step) {
          index = steps.indexOf(step);
          show();
          const details = e.target.closest("details");
          if (details) details.open = true;
        }
      },
      true,
    );
    show();
  }
});
