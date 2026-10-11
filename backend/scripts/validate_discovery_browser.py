"""Actual local BFF/API/worker candidate review; synthetic providers only."""

import argparse
import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8098")
    parser.add_argument("--output", default="tmp/discovery-actual-browser")
    args = parser.parse_args()
    endpoint = urlsplit(args.base_url)
    if endpoint.scheme != "http" or endpoint.hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Local disposable frontend only")
    data = json.loads(Path(args.fixtures).read_text())
    if not all(a["email"].endswith("@example.test") for a in data["accounts"].values()):
        raise SystemExit("Synthetic acceptance accounts only")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as runtime:
        executable = os.getenv(
            "FRONTEND_BROWSER",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        )
        browser = runtime.chromium.launch(
            headless=True,
            executable_path=executable if Path(executable).exists() else None,
        )
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(45000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(args.base_url)
            page.get_by_label("Email", exact=True).fill(
                data["accounts"]["ADMIN"]["email"]
            )
            page.get_by_label("Password").fill(data["accounts"]["ADMIN"]["password"])
            page.get_by_role("button", name="Sign in", exact=True).click()
            page.get_by_role("heading", name="Ready for human review").wait_for()
            wid = data["workspaces"][0]
            page.locator("#workspace").select_option(wid)
            page.get_by_role("heading", name="Ready for human review").wait_for()
            page.get_by_role("link", name="Product setup", exact=True).click()
            page.get_by_label("Describe the real product").fill(
                "Browser discovery acceptance "
                + uuid.uuid4().hex[:8]
                + ": commercial transport scheduling and delivery operations."
            )
            page.get_by_label("Maximum companies per batch").fill("1")
            page.get_by_role("button", name="Continue", exact=True).click()
            page.get_by_role("button", name="Continue", exact=True).click()
            page.get_by_role(
                "button", name="Save offerings & activate", exact=True
            ).click()
            page.get_by_role("heading", name="Jobs & history").wait_for()
            deadline = time.monotonic() + 60
            candidate = None
            while time.monotonic() < deadline:
                found = page.request.get(
                    args.base_url + f"/gateway/{wid}/candidates?status=READY_FOR_REVIEW"
                ).json()
                candidate = next(
                    (c for c in found.get("items", []) if "-browser" in c["domain"]),
                    None,
                )
                if candidate:
                    break
                time.sleep(0.5)
            assert candidate, "Discovery did not persist a review candidate"
            before = page.request.get(args.base_url + f"/gateway/{wid}/leads").json()
            assert all(
                urlsplit(l["website"]).hostname != candidate["domain"] for l in before
            ), "Discovery created a lead before review"
            page.get_by_role("link", name="Discovery", exact=True).click()
            page.get_by_role(
                "heading", name=candidate["company_name"], exact=True
            ).wait_for()
            page.screenshot(
                path=str(output / "candidate-awaiting-review.png"), full_page=True
            )
            with page.expect_response(
                lambda response: response.url.endswith(
                    f"/candidates/{candidate['id']}/accept"
                )
            ) as accepted:
                page.get_by_role(
                    "button", name="Accept & start research", exact=True
                ).click()
            assert accepted.value.status == 200, "BFF acceptance failed"
            result = accepted.value.json()
            detail = page.request.get(
                args.base_url + f"/gateway/{wid}/candidates/{candidate['id']}"
            ).json()
            assert (
                detail["status"] == "ACCEPTED"
                and detail["accepted_lead_id"] == result["lead_id"]
            )
            after = page.request.get(args.base_url + f"/gateway/{wid}/leads").json()
            assert len(after) == len(before) + 1
            assert any(l["id"] == result["lead_id"] for l in after)
            page.get_by_text("No candidates in this view.", exact=False).wait_for()
            page.screenshot(
                path=str(output / "candidate-manually-accepted.png"), full_page=True
            )
            page.get_by_role("button", name="Sign out", exact=True).click()
            assert not errors, errors
        finally:
            browser.close()
    print(
        "PASS actual browser -> BFF -> restricted API/DB -> native workers: product form, discovery candidate, no lead before explicit Accept, one accepted lead/research queue, logout; synthetic providers, no sending"
    )


if __name__ == "__main__":
    main()
