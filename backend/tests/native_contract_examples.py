"""Export deterministic synthetic response examples, never credential/login responses."""

import json
import os
import re
from uuid import UUID
import httpx
from .native_acceptance_check import manifest, login, check


def main():
    data = manifest()
    identifiers = {}

    def stable(value):
        if isinstance(value, dict):
            return {k: stable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [stable(v) for v in value]
        if isinstance(value, str):
            if re.fullmatch(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value
            ):
                identifiers.setdefault(value, str(UUID(int=len(identifiers) + 1)))
                return identifiers[value]
            if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:", value):
                return "2026-10-11T12:00:00Z"
        return value

    with httpx.Client(
        base_url=os.getenv("NATIVE_API_URL", "http://backend-api:8000")
    ) as api:
        headers = login(api, data["accounts"]["ADMIN"])
        prefix = "/workspaces/" + data["workspaces"][0]
        leads = check(
            api.get(prefix + "/leads/page", headers=headers, params={"limit": 2})
        )
        approvals = check(api.get(prefix + "/approvals", headers=headers))
        jobs = check(api.get(prefix + "/jobs", headers=headers))
        value = {
            "source": "Isolated actual native acceptance responses; synthetic data; IDs/times normalized.",
            "current_user": check(api.get("/auth/me", headers=headers)),
            "workspaces": check(api.get("/workspaces", headers=headers)),
            "catalog_all": check(api.get(prefix + "/catalog/all", headers=headers)),
            "lead_detail": leads["items"][0],
            "lead_page": leads,
            "approval": approvals[0],
            "job": jobs[0],
        }
        value["lead_page"]["next_cursor"] = "example-opaque-cursor-redacted"
        # A cursor encodes original IDs/timestamps; never suggest the normalized example is executable.
        print(json.dumps(stable(value), indent=2))


if __name__ == "__main__":
    main()
