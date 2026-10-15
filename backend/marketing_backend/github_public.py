"""Bounded, unauthenticated GitHub enrichment for public company research."""
import re
from urllib.parse import urlsplit
import httpx

API = "https://api.github.com"
# GitHub links commonly use either the canonical /orgs/{login} form or the
# short github.com/{login} form. The API lookup below filters profile paths
# that are not organizations.
ORG_RE = re.compile(r"^/(?:orgs/)?([A-Za-z0-9][A-Za-z0-9-]*)/?$")


def organization_slugs(urls):
    slugs = []
    for raw in urls:
        parsed = urlsplit(raw)
        if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
            continue
        match = ORG_RE.match(parsed.path)
        if match and match.group(1).lower() not in {"settings", "login", "features"}:
            slug = match.group(1)
            if slug.lower() not in {s.lower() for s in slugs}:
                slugs.append(slug)
    return slugs[:2]


def _get(client, path):
    response = client.get(f"{API}{path}", headers={"Accept": "application/vnd.github+json"})
    if response.status_code in (403, 404, 429):
        return None
    response.raise_for_status()
    return response.json()


def enrich(urls, timeout=5.0):
    """Return source pages from linked public GitHub organizations.

    An empty result is normal: GitHub is optional and never blocks research.
    """
    pages = []
    for slug in organization_slugs(urls):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                org = _get(client, f"/orgs/{slug}")
                members = _get(client, f"/orgs/{slug}/public_members?per_page=5")
        except (httpx.HTTPError, ValueError, TypeError):
            continue
        if not isinstance(org, dict):
            continue
        org_url = f"{API}/orgs/{slug}"
        org_text = " ".join(
            f"{key}: {org[key]}" for key in ("name", "login", "description", "blog", "location")
            if org.get(key)
        )
        if org_text:
            pages.append({"source_url": org_url, "text": org_text, "links": []})
        if isinstance(members, list):
            for member in members:
                if not isinstance(member, dict) or not member.get("login"):
                    continue
                login = member["login"]
                try:
                    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                        profile = _get(client, f"/users/{login}")
                except (httpx.HTTPError, ValueError, TypeError):
                    profile = None
                fields = [f"GitHub public member login: {login}"]
                if isinstance(profile, dict):
                    for key, label in (("name", "name"), ("bio", "bio"), ("company", "company"), ("location", "location")):
                        if profile.get(key):
                            fields.append(f"{label}: {profile[key]}")
                fields.append(f"profile: https://github.com/{login}")
                pages.append({
                    "source_url": f"https://github.com/{login}",
                    "text": "; ".join(fields),
                    "links": [],
                })
    return pages[:7]
