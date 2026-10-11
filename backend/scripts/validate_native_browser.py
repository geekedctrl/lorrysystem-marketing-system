"""Browser acceptance against the actual disposable native API/worker stack.

Requires Playwright, a private synthetic account manifest and a localhost frontend.
Unlike the frontend owner's mock suite, no upstream API transport is replaced here.
"""

import argparse
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8095")
    parser.add_argument("--output", default="tmp/native-actual-browser")
    args = parser.parse_args()
    endpoint = urlsplit(args.base_url)
    if endpoint.hostname not in ("127.0.0.1", "localhost") or endpoint.scheme != "http":
        raise SystemExit("Acceptance browser runner only accepts localhost HTTP")
    data = json.loads(Path(args.fixtures).read_text())
    if not all(a["email"].endswith("@example.test") for a in data["accounts"].values()):
        raise SystemExit("Only synthetic example.test acceptance accounts are allowed")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        executable = os.getenv(
            "FRONTEND_BROWSER",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        )
        browser = p.chromium.launch(
            headless=True,
            executable_path=executable if Path(executable).exists() else None,
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(45000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("dialog", lambda dialog: dialog.accept())

        def sign_in(role):
            page.goto(args.base_url)
            page.get_by_label("Email", exact=True).fill(data["accounts"][role]["email"])
            page.get_by_label("Password").fill(data["accounts"][role]["password"])
            page.get_by_role("button", name="Sign in", exact=True).click()
            page.get_by_role("heading", name="Ready for human review").wait_for()

        sign_in("ADMIN")
        page.screenshot(path=str(output / "actual-overview.png"), full_page=True)
        page.locator("#workspace").select_option(data["workspaces"][0])
        page.get_by_role("heading", name="Ready for human review").wait_for()
        page.get_by_role("link", name="Product setup", exact=True).click()
        page.get_by_role("button", name="Continue", exact=True).click()
        page.get_by_role("button", name="Continue", exact=True).click()
        with page.expect_response(
            lambda r: r.url.endswith("/automation/activate")
        ) as activated:
            page.get_by_role(
                "button", name="Save offerings & activate", exact=True
            ).click()
        assert activated.value.status == 202
        setup_id = activated.value.json()["job_id"]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            job = page.request.get(
                args.base_url
                + "/gateway/"
                + data["workspaces"][0]
                + "/jobs/"
                + setup_id
            ).json()
            if job["status"] == "COMPLETED":
                break
            time.sleep(0.4)
        else:
            raise AssertionError("Browser form setup did not complete")
        for index, wid in enumerate(data["workspaces"]):
            page.locator("#workspace").select_option(wid)
            page.get_by_role("heading", name="Ready for human review").wait_for()
            page.get_by_role("link", name="Leads", exact=True).click()
            company = "Synthetic Accounting" if index else "Synthetic Haulage"
            row = page.locator("tr").filter(has_text=company)
            row.get_by_role("button", name="Open lead", exact=True).click()
            page.get_by_role(
                "button", name="Start fresh preparation", exact=False
            ).click()
            page.get_by_role("tab", name="Research", exact=True).click()
            page.get_by_text("Industry:", exact=False).wait_for()
            page.get_by_role("tab", name="People", exact=True).click()
            page.get_by_text("Casey Sample", exact=True).first.wait_for()
            page.get_by_role("tab", name="Qualification", exact=True).click()
            page.get_by_role("heading", name="Score 85/100").wait_for()
            page.get_by_role("tab", name="Outreach", exact=True).click()
            page.get_by_label("Review note (required for every decision)").fill(
                "Reviewed synthetic source evidence, product, recipient and exact draft"
            )
            page.get_by_role("button", name="Approve draft", exact=True).click()
            page.get_by_text(
                "Decision saved. No message was sent.", exact=True
            ).wait_for()
            page.screenshot(
                path=str(output / f"actual-approved-product-{index + 1}.png"),
                full_page=True,
            )
        page.get_by_role("link", name="Activity & operations", exact=True).click()
        page.get_by_role("heading", name="Jobs & history").wait_for()
        page.get_by_role("link", name="Product setup", exact=True).click()
        page.get_by_role("button", name="Pause automation", exact=True).click()
        page.get_by_role("button", name="Resume automation", exact=True).wait_for()
        page.get_by_role("button", name="Resume automation", exact=True).click()
        page.get_by_role("button", name="Pause automation", exact=True).wait_for()
        page.get_by_role("link", name="Leads", exact=True).click()
        for width, height, name in [(1024, 768, "tablet"), (390, 844, "mobile")]:
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), "Page overflow"
            page.screenshot(path=str(output / f"actual-{name}.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.get_by_role("button", name="Sign out", exact=True).click()
        page.get_by_role("heading", name="Welcome back").wait_for()
        for role in ("OPERATOR", "REVIEWER", "VIEWER"):
            sign_in(role)
            assert not page.get_by_role(
                "link", name="Product setup", exact=True
            ).count()
            page.get_by_role("link", name="Discovery", exact=True).click()
            page.get_by_role(
                "heading", name="Find your next customers", exact=True
            ).wait_for()
            assert page.get_by_role(
                "button", name="Find leads", exact=True
            ).count() == (1 if role == "OPERATOR" else 0)
            page.get_by_role("button", name="Sign out", exact=True).click()
            page.get_by_role("heading", name="Welcome back").wait_for()
        assert not errors, errors
        browser.close()
    print(
        "PASS: headless browser -> actual BFF/API/PostgreSQL/workers, two products, research/people/scoring/drafts, synthetic approval without sending, pause/resume, four roles, tablet/mobile layouts; screenshots saved"
    )


if __name__ == "__main__":
    main()
