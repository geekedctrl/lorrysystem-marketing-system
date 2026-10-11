"""Exercise new contracts/revisions/lifecycle using actual restricted API role over HTTP."""

import copy
import os
import uuid
import httpx
from .native_acceptance_check import manifest, login, check


def main():
    data = manifest()
    wid = data["workspaces"][0]
    prefix = "/workspaces/" + wid
    with httpx.Client(
        base_url=os.getenv("NATIVE_API_URL", "http://backend-api:8000"), timeout=20
    ) as api:
        admin = login(api, data["accounts"]["ADMIN"])
        reviewer = login(api, data["accounts"]["REVIEWER"])
        assert not check(api.get("/auth/me", headers=admin))["capabilities"][
            "create_workspace"
        ]
        page = check(
            api.get(prefix + "/leads/page", headers=admin, params={"limit": 2})
        )
        assert page["total"] >= 3 and page["next_cursor"]
        detail = check(
            api.get(prefix + "/leads/" + page["items"][0]["id"], headers=admin)
        )
        assert detail["current_preparation"]
        approvals = check(api.get(prefix + "/approvals", headers=admin))
        parent = next(
            a for a in approvals if a["status"] == "PENDING" and not a["stale"]
        )
        snapshot = copy.deepcopy(parent["snapshot"])
        decision_path = prefix + "/approvals/" + parent["id"] + "/decision"
        check(
            api.post(
                decision_path,
                headers=reviewer,
                json={
                    "decision": "CHANGES_REQUESTED",
                    "note": "Please keep the opening concise and sourced",
                },
            )
        )
        body = {
            "idempotency_key": uuid.uuid4().hex,
            "expected_version": parent["version"],
            "subject": "A brief capability discussion",
            "body": snapshot["draft"]["body"]
            + "\n\nHappy to share the documented capabilities.",
            "evidence": snapshot["draft"]["evidence"],
            "note": "Updated the wording following the reviewer note",
        }
        revision_path = prefix + "/approvals/" + parent["id"] + "/revision"
        fresh = check(api.post(revision_path, headers=admin, json=body), 201)
        assert check(api.post(revision_path, headers=admin, json=body), 201) == fresh
        fresh_path = prefix + "/approvals/" + fresh["approval_id"] + "/decision"
        decision = {
            "decision": "APPROVED",
            "note": "Reviewed the saved revised draft and recipient",
        }
        check(api.post(fresh_path, headers=admin, json=decision), 403)
        assert (
            check(api.post(fresh_path, headers=reviewer, json=decision))["sent"]
            is False
        )
        saved = check(api.get(prefix + "/approvals", headers=admin))
        assert next(a for a in saved if a["id"] == parent["id"])["snapshot"] == snapshot
        product = next(
            c
            for c in check(api.get(prefix + "/catalog/all", headers=admin))
            if c["kind"] == "PRODUCT"
        )
        lifecycle_path = prefix + "/catalog/" + product["id"]
        check(api.patch(lifecycle_path, headers=admin, json={"active": False}))
        assert not check(api.get(prefix + "/operations", headers=admin))["enabled"]
        check(api.post(prefix + "/automation/resume", headers=admin), 409)
        check(api.patch(lifecycle_path, headers=admin, json={"active": True}))
        check(api.post(prefix + "/automation/resume", headers=admin))
        saved = check(api.get(prefix + "/approvals", headers=admin))
        assert next(a for a in saved if a["id"] == fresh["approval_id"])["stale"]
    print(
        "PASS: actual restricted API role, typed user/lead paging, immutable idempotent revision, separate reviewer, catalog lifecycle and persistent stale context; sent:false"
    )


if __name__ == "__main__":
    main()
