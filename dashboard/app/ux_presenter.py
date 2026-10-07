"""Plain-language preparation summaries from current saved pipeline state."""


def preparation_summary(lead, state, actions=None):
    if lead.get("status") in ("CONVERTED", "DISQUALIFIED", "LOST"):
        return {
            "label": lead["status"].replace("_", " ").title(),
            "tone": "status",
            "next": "View history",
        }
    jobs = state.get("automation_jobs") or []
    active = next(
        (job for job in jobs if job["status"] in ("RUNNING", "PENDING")), None
    )
    if active:
        return {
            "label": active["kind"].title()
            + (" in progress" if active["status"] == "RUNNING" else " queued"),
            "tone": "status",
            "next": "Monitor progress",
        }
    latest = jobs[0] if jobs else {}
    if latest.get("status") in ("FAILED", "NEEDS_REVIEW"):
        return {
            "label": "Needs attention",
            "tone": "warning",
            "next": "Review evidence or contact",
        }
    statuses = {action.get("status") for action in (actions or [])}
    if "PENDING_APPROVAL" in statuses:
        return {
            "label": "Awaiting approval",
            "tone": "warning",
            "next": "Review outreach",
        }
    if "DRAFT" in statuses:
        return {
            "label": "Draft needs review",
            "tone": "warning",
            "next": "Review outreach",
        }
    if "APPROVED" in statuses:
        return {
            "label": "Outreach approved",
            "tone": "success",
            "next": "View approved outreach",
        }
    if statuses.intersection({"SENT", "PUBLISHED"}):
        return {
            "label": "Outreach delivered",
            "tone": "success",
            "next": "View outreach history",
        }
    if latest.get("outcome") in (
        "BELOW_QUALIFICATION_THRESHOLD",
        "NO_SUPPORTED_PRODUCT_MATCH",
        "SCORING_CONTEXT_CHANGED",
    ):
        return {
            "label": "Fit needs review",
            "tone": "warning",
            "next": "Review qualification",
        }
    if state.get("managed") and not state.get("automation_enabled"):
        return {
            "label": "Automation paused",
            "tone": "warning",
            "next": "Ask an administrator to resume",
        }
    if state.get("matching_current"):
        return {"label": "Products matched", "tone": "success", "next": "View outreach"}
    if state.get("scored"):
        return {"label": "Scored", "tone": "success", "next": "Review qualification"}
    return {
        "label": "Preparing" if state.get("managed") else "Research & review",
        "tone": "status",
        "next": "View preparation",
    }
