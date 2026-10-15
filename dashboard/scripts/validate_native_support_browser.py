"""New support controls against the actual disposable native integration stack.

Requires private accounts exported from native-acceptance bootstrap. No API mocking.
Mutates synthetic preparation/approvals/catalog; never run against existing app data.
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
    parser.add_argument("--output", default="tmp/native-support-browser")
    args = parser.parse_args()
    endpoint = urlsplit(args.base_url)
    if endpoint.hostname not in {"localhost", "127.0.0.1"} or endpoint.scheme != "http":
        raise SystemExit("Only the local synthetic acceptance frontend is allowed")
    data = json.loads(Path(args.fixtures).read_text())
    if not all(account["email"].endswith("@example.test") for account in data["accounts"].values()):
        raise SystemExit("Only native-acceptance synthetic accounts are allowed")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        executable = os.getenv("FRONTEND_BROWSER", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
        browser = p.chromium.launch(headless=True, executable_path=executable if Path(executable).exists() else None)
        page = browser.new_page(viewport={"width":1440,"height":1000})
        page.set_default_timeout(45000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("dialog", lambda dialog: dialog.accept())
        wid = data["workspaces"][0]
        gateway = args.base_url + "/gateway/" + wid + "/"

        def sign_in(role):
            page.goto(args.base_url)
            page.get_by_label("Email", exact=True).fill(data["accounts"][role]["email"])
            page.get_by_label("Password").fill(data["accounts"][role]["password"])
            page.get_by_role("button", name="Sign in", exact=True).click()
            page.get_by_role("heading", name="Ready for human review").wait_for()
            session = page.request.get(args.base_url+"/session").json()
            assert session["user"]["email"].endswith("@example.test")
            assert all("Acceptance" in w["name"] for w in session["workspaces"])
            assert not session["user"]["capabilities"]["create_workspace"]
            assert "token" not in session["user"]
            page.locator("#workspace").select_option(wid)
            page.get_by_role("heading", name="Ready for human review").wait_for()

        sign_in("ADMIN")
        print("Actual support: profile and permissions verified",flush=True)
        lead_page = page.request.get(gateway+"leads/page?limit=1").json()
        assert lead_page["next_cursor"] and lead_page["total"] > 1
        next_response = page.request.get(gateway+"leads/page",params={"limit":1,"cursor":lead_page["next_cursor"]})
        assert next_response.status==200
        assert next_response.json()["items"][0]["id"]!=lead_page["items"][0]["id"]
        page.get_by_role("link",name="Leads",exact=True).click()
        page.get_by_label("Search companies",exact=True).fill("Synthetic Haulage")
        page.get_by_role("button",name="Apply filters",exact=True).click()
        page.get_by_role("link",name="Synthetic Haulage",exact=True).wait_for()
        assert page.get_by_role("button",name="Next page",exact=True).is_disabled()
        page.get_by_role("link",name="Synthetic Haulage",exact=True).click()
        page.get_by_role("heading",name="Synthetic Haulage",exact=True).wait_for()
        with page.expect_response(lambda r:r.url.endswith("/prepare")) as prepared:
            page.get_by_role("button",name="Start fresh preparation",exact=True).click()
        assert prepared.value.status==202
        run_id=prepared.value.json()["run_id"]
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            run=page.request.get(gateway+"preparation/"+run_id).json()
            if run["status"]=="PENDING_APPROVAL":break
            assert run["status"] not in {"FAILED","NEEDS_REVIEW","STALE"},run.get("stop_reason")
            time.sleep(.5)
        else:raise AssertionError("Native preparation did not reach approval")
        # Return to the filtered list, retaining context; reload detail after work completes.
        page.get_by_role("button",name="Back to leads",exact=False).click()
        assert page.get_by_label("Search companies",exact=True).input_value()=="Synthetic Haulage"
        page.get_by_role("link",name="Synthetic Haulage",exact=True).click()
        page.get_by_role("tab",name="Outreach",exact=True).click()
        page.get_by_label("Review note (required for every decision)",exact=True).fill("Please make the opening more concise")
        with page.expect_response(lambda r:r.url.endswith("/decision")) as decision:
            page.get_by_role("button",name="Request changes",exact=True).click()
        assert decision.value.json()["sent"] is False
        page.get_by_text("Edit requested changes",exact=True).click()
        page.get_by_label("Revised subject",exact=True).fill("A concise, sourced capability discussion")
        page.get_by_label("Revision note",exact=True).fill("Shortened the opening following reviewer feedback")
        with page.expect_response(lambda r:r.url.endswith("/revision")) as revised:
            page.get_by_role("button",name="Submit revision for review",exact=True).click()
        assert revised.value.status==201
        revision=revised.value.json()
        assert revision["sent"] is False
        page.get_by_text("You edited this version.",exact=False).wait_for()
        assert page.get_by_role("button",name="Approve draft",exact=True).is_disabled()
        saved=page.request.get(gateway+"approvals").json()
        child=next(a for a in saved if a["id"]==revision["approval_id"])
        parent_id=child["snapshot"]["revision"]["parent_approval_id"]
        parent=next(a for a in saved if a["id"]==parent_id)
        assert parent["snapshot"]["draft"]["subject"]!=child["snapshot"]["draft"]["subject"]
        assert child["snapshot"]["revision"]["reviewer_note"]=="Please make the opening more concise"
        page.screenshot(path=str(output/"actual-human-revision.png"),full_page=True)
        page.get_by_role("button",name="Sign out",exact=True).click()
        sign_in("REVIEWER")
        page.get_by_role("link",name="Leads",exact=True).click()
        page.get_by_label("Search companies",exact=True).fill("Synthetic Haulage")
        page.get_by_role("button",name="Apply filters",exact=True).click()
        page.get_by_role("link",name="Synthetic Haulage",exact=True).click()
        page.get_by_role("tab",name="Outreach",exact=True).click()
        page.get_by_label("Review note (required for every decision)",exact=True).fill("Separately reviewed the revised draft and saved evidence")
        with page.expect_response(lambda r:r.url.endswith("/decision")) as approved:
            page.get_by_role("button",name="Approve draft",exact=True).click()
        assert approved.value.status==200 and approved.value.json()["sent"] is False
        page.get_by_text("Decision saved. No message was sent.",exact=True).wait_for()
        print("Actual support: native preparation, immutable revision and separate reviewer verified",flush=True)
        page.get_by_role("button",name="Sign out",exact=True).click()
        sign_in("ADMIN")
        page.get_by_role("link",name="Settings",exact=True).click()
        page.get_by_role("button",name="Automation",exact=True).click()
        page.get_by_role("button",name="Pause automation",exact=True).click()
        page.get_by_role("button",name="Resume automation",exact=True).wait_for()
        page.get_by_role("button",name="Product",exact=True).click()
        catalog=page.request.get(gateway+"catalog/all").json()
        product=next(c for c in catalog if c["kind"]=="PRODUCT" and c["active"])
        page.get_by_role("button",name="Deactivate "+product["name"],exact=True).click()
        page.get_by_role("button",name="Reactivate "+product["name"],exact=True).wait_for()
        page.get_by_role("button",name="Reactivate "+product["name"],exact=True).click()
        page.get_by_role("button",name="Deactivate "+product["name"],exact=True).wait_for()
        after=page.request.get(gateway+"catalog/all").json()
        assert next(c for c in after if c["id"]==product["id"])["version"]==product["version"]+2
        page.get_by_role("button",name="Resume automation",exact=True).click()
        page.get_by_role("button",name="Pause automation",exact=True).wait_for()
        approvals=page.request.get(gateway+"approvals").json()
        assert next(a for a in approvals if a["id"]==revision["approval_id"])["stale"]
        page.screenshot(path=str(output/"actual-catalog-lifecycle.png"),full_page=True)
        assert not errors,errors
        page.get_by_role("button",name="Sign out",exact=True).click()
        browser.close()
    print("PASS: actual profile, paging/search/detail, current preparation, sourced immutable revision, separate review, catalog lifecycle and persistent stale context; no sending")


if __name__=="__main__":
    main()
