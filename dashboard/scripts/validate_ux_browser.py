import sys, json, secrets
from pathlib import Path
import argparse

parser = argparse.ArgumentParser(
    description="Local browser regression using disposable native workflow fixtures"
)
parser.add_argument("--fixtures", required=True)
parser.add_argument("--base-url", default="http://127.0.0.1:8091")
parser.add_argument("--api-url", default="http://127.0.0.1:8011")
parser.add_argument("--browser", default=None)
parser.add_argument("--artifacts", default="tmp/ux-review")
args = parser.parse_args()
from urllib.parse import urlsplit
for url in (args.base_url, args.api_url):
    if urlsplit(url).hostname not in ("localhost", "127.0.0.1", "::1"):
        parser.error("This mutating validation is restricted to disposable localhost services.")
artifacts = Path(args.artifacts)
artifacts.mkdir(parents=True, exist_ok=True)
from playwright.sync_api import sync_playwright

data = json.loads(Path(args.fixtures).read_text())
account = data["account"]
f = data["fixtures"][0]
with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path=args.browser
        or (
            "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
            if Path(
                "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
            ).exists()
            else None
        ),
        headless=True,
    )
    page = b.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(args.base_url + "/login")
    page.locator("[name=email]").fill(account["email"])
    page.locator("[name=password]").fill(account["password"])
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/dashboard")
    page.locator("#workspace-switch").select_option(f["wid"])
    page.get_by_role("button", name="Switch workspace").click()
    for path in [
        "/dashboard",
        "/leads",
        "/discovered-leads",
        "/actions",
        "/approvals",
        "/workspaces?section=product",
        "/workspaces?section=team",
        "/workspaces?section=integrations",
        "/workspaces?section=account",
        "/leads/" + f["lead"],
        "/leads/new",
        "/leads/new/manual",
        "/leads/import",
        "/system",
    ]:
        response = page.goto(args.base_url + path)
        assert response.status == 200, (
            path,
            response.status,
            page.locator("body").inner_text()[:400],
        )
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), path
        if "/leads/" + f["lead"] == path:
            assert (
                page.get_by_role("tab", name="Overview", exact=True).get_attribute(
                    "aria-selected"
                )
                == "true"
            )
            for tab in ["Research", "People", "Qualification", "Outreach", "Activity"]:
                page.get_by_role("tab", name=tab, exact=True).click()
                assert page.get_by_role("tabpanel").filter(visible=True).count() == 1
            page.screenshot(path=str(artifacts / "lead-desktop.png"), full_page=True)
    page.goto(args.base_url + "/workspaces?section=product")
    page.get_by_role("button", name="Continue", exact=True).click()
    assert page.locator("[data-step]").nth(1).is_visible()
    page.get_by_role("button", name="Continue", exact=True).click()
    assert page.locator("[data-step]").nth(2).is_visible()
    page.get_by_role("button", name="Back", exact=True).click()
    assert page.locator("[data-step]").nth(1).is_visible()
    page.get_by_role("button", name="Back", exact=True).click()
    assert page.locator("[data-step]").nth(0).is_visible()
    page.evaluate("marketingTheme('dark')")
    page.screenshot(path=str(artifacts / "setup-dark.png"), full_page=True)
    page.reload()
    assert page.locator("html").get_attribute("data-theme") == "dark"
    # Back links retain list filters; hash navigation reveals hidden source/section tabs.
    page.goto(args.base_url + "/leads?q=Native&sort=score&page_number=1")
    page.goto(args.base_url + "/leads/" + f["lead"] + "#lead-actions")
    assert (
        page.get_by_role("tab", name="Outreach", exact=True).get_attribute(
            "aria-selected"
        )
        == "true"
    )
    assert "sort=score" in page.locator('[data-parent="leads"]').get_attribute("href")
    page.get_by_role("tab", name="Research", exact=True).focus()
    page.keyboard.press("ArrowRight")
    assert (
        page.get_by_role("tab", name="People", exact=True).get_attribute(
            "aria-selected"
        )
        == "true"
    )
    page.goto(args.base_url + "/workspaces?section=product")
    page.locator("[name=product_type]").fill("Unsaved service product")
    page.get_by_role("button", name="Continue", exact=True).click()
    page.get_by_role("button", name="Back", exact=True).click()
    assert (
        page.locator("[name=product_type]").input_value() == "Unsaved service product"
    )
    # Test actual onboarding in the disposable database; no worker/providers are running.
    page.goto(args.base_url + "/workspaces?section=account")
    form = page.locator("form").filter(has=page.locator("[name=action][value=create]"))
    form.locator("[name=name]").fill("UX local " + secrets.token_hex(4))
    form.get_by_role("button", name="Create workspace").click()
    page.goto(args.base_url + "/workspaces?section=product")
    page.get_by_role("button", name="Continue", exact=True).click()
    assert page.locator("[data-step]").nth(0).is_visible(), "Invalid step advanced"
    page.locator("[name=product_type]").fill("Service management software")
    page.locator("[name=description]").fill(
        "Project and billing management software for professional service businesses."
    )
    page.get_by_role("button", name="Continue", exact=True).click()
    page.locator("[name=offering_name]").fill("Service Pro")
    page.locator("[name=offering_description]").fill(
        "Project tracking and customer billing for professional service teams."
    )
    page.get_by_role("button", name="Add another offering").click()
    assert page.locator("#product-offerings .product-offering").count() == 2
    page.locator("#product-offerings .product-offering").last.get_by_role(
        "button", name="Remove offering"
    ).click()
    page.get_by_role("button", name="Continue", exact=True).click()
    assert "Service Pro" in page.locator("[data-setup-review]").inner_text()
    page.get_by_role("button", name="Activate product", exact=True).click()
    assert page.get_by_text("Configuring", exact=True).is_visible()
    page.get_by_role("button", name="Pause automation", exact=True).click()
    assert page.get_by_text("Paused", exact=True).is_visible()
    # Server rejection preserves catalog and product inputs.
    page.goto(args.base_url + "/workspaces?section=product")
    form = page.locator("form[data-wizard]")
    csrf = form.locator("[name=csrf_token]").input_value()
    response = page.request.post(
        args.base_url + "/workspaces/manage",
        form={
            "csrf_token": csrf,
            "action": "activate-product",
            "product_type": "Preserved invalid setup",
            "description": "Project management software for professional service teams.",
            "country_code": "MY",
            "language": "English",
            "daily_new_companies": "11",
            "offering_id": "",
            "offering_name": "Preserved offering",
            "offering_description": "Project billing and supported team operations.",
        },
    )
    assert (
        "Preserved invalid setup" in response.text()
        and "Preserved offering" in response.text()
    )
    # Verify read-only access with a new disposable viewer account.
    login_response = page.request.post(args.api_url + "/api/auth/login", data=account)
    assert login_response.ok
    headers = {
        "Authorization": "Bearer " + login_response.json()["token"],
        "X-Workspace-ID": f["wid"],
    }
    viewer = {
        "email": "ux-viewer-" + secrets.token_hex(6) + "@example.invalid",
        "password": secrets.token_urlsafe(24),
    }
    invite = page.request.post(
        args.api_url + "/api/workspaces/" + f["wid"] + "/invitations",
        headers=headers,
        data={"email": viewer["email"], "role": "VIEWER"},
    )
    assert invite.ok
    accepted = page.request.post(
        args.api_url + "/api/auth/invitations/accept",
        data={"token": invite.json()["token"], "password": viewer["password"]},
    )
    assert accepted.ok
    context = b.new_context(viewport={"width": 1280, "height": 900})
    readonly = context.new_page()
    readonly.goto(args.base_url + "/login")
    readonly.locator("[name=email]").fill(viewer["email"])
    readonly.locator("[name=password]").fill(viewer["password"])
    readonly.get_by_role("button", name="Sign in").click()
    readonly.wait_for_url("**/dashboard")
    readonly.goto(args.base_url + "/leads")
    assert readonly.get_by_role("link", name="+ Add Lead", exact=True).count() == 0
    assert (
        readonly.locator(".app-nav")
        .get_by_role("link", name="Product setup", exact=True)
        .count()
        == 0
    )
    readonly.goto(args.base_url + "/workspaces?section=product")
    assert readonly.get_by_text(
        "Administrator access required", exact=True
    ).is_visible()
    context.close()
    page.locator("#workspace-switch").select_option(f["wid"])
    page.get_by_role("button", name="Switch workspace").click()
    # Review screen is reachable and approvals never imply sending.
    actions = page.request.get(
        args.api_url + "/api/leads/" + f["lead"] + "/actions", headers=headers
    ).json()
    for action in actions:
        approvals = page.request.get(
            args.api_url + "/api/actions/" + action["id"] + "/approvals",
            headers=headers,
        ).json()
        if approvals:
            page.goto(args.base_url + "/approvals/" + approvals[0]["id"])
            assert page.get_by_text(
                "Approval records your decision. Sending is a separate stage."
            ).is_visible()
            if approvals[0]["status"] == "PENDING":
                page.get_by_role("button", name="Approve", exact=True).click()
                assert page.get_by_text("Decision saved successfully.").is_visible()
                saved = page.request.get(
                    args.api_url + "/api/leads/" + f["lead"] + "/actions",
                    headers=headers,
                ).json()
                assert (
                    next(x for x in saved if x["id"] == action["id"])["status"]
                    == "APPROVED"
                )
            break
    # Return to the original completed test workspace for layout checks.
    page.locator("#workspace-switch").select_option(f["wid"])
    page.get_by_role("button", name="Switch workspace").click()
    page.set_viewport_size({"width": 390, "height": 844})
    for path in [
        "/dashboard",
        "/leads",
        "/workspaces?section=product",
        "/workspaces?section=team",
        "/leads/" + f["lead"],
        "/leads/import",
    ]:
        page.goto(args.base_url + path)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
            "mobile",
            path,
        )
    page.get_by_role("button", name="Open navigation").click()
    assert page.locator("body").evaluate("e=>e.classList.contains('nav-open')")
    page.keyboard.press("Escape")
    assert not page.locator("body").evaluate("e=>e.classList.contains('nav-open')")
    page.goto(args.base_url + "/leads/" + f["lead"])
    page.get_by_role("tab", name="Overview", exact=True).click()
    page.screenshot(path=str(artifacts / "lead-mobile.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.evaluate("marketingTheme('light')")
    page.get_by_role("tab", name="Research", exact=True).click()
    page.screenshot(path=str(artifacts / "research-light.png"), full_page=True)
    page.goto(args.base_url + "/dashboard")
    page.screenshot(path=str(artifacts / "overview-light.png"), full_page=True)
    page.set_viewport_size({"width": 768, "height": 1024})
    page.goto(args.base_url + "/workspaces?section=team")
    assert page.evaluate(
        "document.documentElement.scrollWidth<=innerWidth"
    ), "Tablet overflow"
    page.goto(args.base_url + "/leads?q=definitely-no-company-" + secrets.token_hex(4))
    assert page.get_by_text("No Leads found.", exact=True).is_visible()
    for key in ["light", "dark"]:
        page.evaluate("marketingTheme(" + json.dumps(key) + ")")
        assert page.locator("html").get_attribute("data-theme") == key

    assert not errors, errors
    b.close()
print(
    "PASS desktop/tablet/mobile routes, themes, keyboard tabs and drawer, setup activation/validation retention, viewer access, approval without sending, filtered back links and empty states; no browser errors"
)
