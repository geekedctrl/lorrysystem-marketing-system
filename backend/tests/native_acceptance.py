"""Fail-closed synthetic bootstrap/worker for the disposable native acceptance DB only.

Production worker code, restricted roles, leases, stage validation and reservations stay real.
Only evidence fetching and provider responses are synthetic; no provider HTTP calls occur.
"""

import argparse
import json
import os
import secrets
import re
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import select
from marketing_backend.db import Session, engine
from marketing_backend.models import User, Workspace, Membership
from marketing_backend.auth import hash_password
from marketing_backend.providers import Providers
from marketing_backend.research import ProviderFailure


def guard():
    if (
        os.getenv("APP_ENV") != "native-acceptance"
        or engine.url.database != "marketing_native_acceptance"
    ):
        raise RuntimeError(
            "Synthetic runtime requires the dedicated marketing_native_acceptance DB and APP_ENV"
        )


def company(url):
    accounting = "accounting" in url
    name = "Synthetic Accounting" if accounting else "Synthetic Haulage"
    # Extra cases are deterministic and must use these synthetic URL hosts only.
    if "contact-review" in url:
        name = "Contact Review Haulage"
    if "provider-failure" in url:
        name = "Provider Failure Haulage"
    service = f"{name} provides " + (
        "accounting and invoice processing services."
        if accounting
        else "commercial transport and delivery services."
    )
    need = f"{name} reports " + (
        "manual invoice entry and reconciliation delays."
        if accounting
        else "delayed deliveries and manual route planning."
    )
    signal = f"{name} is seeking a new " + (
        "invoice reconciliation system."
        if accounting
        else "transport scheduling system."
    )
    person = "Casey Sample is Operations Director. Contact Casey Sample at casey@fixtures.example.org."
    return name, service, need, signal, person


def synthetic_fetch(url):
    from urllib.parse import urlsplit

    if not urlsplit(url).hostname.endswith(".fixtures.example.org"):
        raise RuntimeError("Synthetic acceptance cannot fetch a real company URL")
    _, service, need, signal, person = company(url)
    return {
        "fetch_status": "SUCCESS",
        "final_url": url,
        "body": "<p>"
        + " ".join((service, need, signal, person, "Existing systems remain in place."))
        + "</p>",
    }


class SyntheticProviders(Providers):
    def ready(self, search=False):
        guard()

    def search(self, operation, query, **options):
        key = "search:" + operation
        if key in self.cache:
            return self.cache[key]
        uid = self.reserve("BRAVE", operation, 0)
        rows = []
        if operation.startswith("discovery"):
            accounting = "accounting" in json.dumps(self.job.payload["context"]).lower()
            marker = re.search(r"browser discovery acceptance ([a-z0-9]{8})", json.dumps(self.job.payload["context"]).lower())
            suffix = "-browser-" + marker[1] if marker else ""
            url = "https://" + ("accounting" if accounting else "haulage") + suffix + ".fixtures.example.org/"
            name, service, *_ = company(url)
            rows = [{"url": url, "title": name, "text": service}]
        elif "contact-review" in self.job.payload.get(
            "website", ""
        ) and operation.endswith("linkedin"):
            name = self.job.payload["company_name"]
            rows = [
                {
                    "url": f"https://www.linkedin.com/in/casey-synthetic-{n}",
                    "title": f"Casey Sample — {name}",
                    "text": "Operations Director",
                }
                for n in (1, 2)
            ]
        self.record(uid, "SUCCESS")
        return self.remember(key, rows)

    def model(self, operation, instructions, data):
        key = "model:" + operation
        if key in self.cache:
            return self.cache[key]
        uid = self.reserve("MODEL", operation, 0)
        if (
            "provider-failure" in self.job.payload.get("website", "")
            and operation == "research"
            and not any(
                e.get("code") == "SYNTHETIC_PROVIDER_FAILURE" for e in self.job.history
            )
        ):
            self.record(uid, "REJECTED")
            raise ProviderFailure("SYNTHETIC_PROVIDER_FAILURE")
        if operation == "setup":
            accounting = "accounting" in json.dumps(data).lower()
            icps = (
                []
                if any(
                    c["kind"] == "ICP" for c in self.job.payload["context"]["catalog"]
                )
                else [
                    {
                        "code": "ICP",
                        "name": (
                            "Accounting firms" if accounting else "Transport operators"
                        ),
                        "description": "Companies with publicly documented relevant business operations",
                    }
                ]
            )
            value = {
                "discovery_query": (
                    "Accounting businesses"
                    if accounting
                    else "Commercial transport businesses"
                ),
                "icps": icps,
            }
        else:
            url = (
                self.job.payload.get("website")
                or (data.get("pages") or data.get("excerpts"))[0]["source_url"]
            )
            name, service, need, signal, person = company(url)
            citation = lambda quote: {"source_url": url, "evidence_quote": quote}
            if operation.startswith("discovery:"):
                icp = next(
                    c["code"]
                    for c in self.job.payload["context"]["catalog"]
                    if c["kind"] == "ICP"
                )
                value = dict(
                    suitable=True,
                    company_name=name,
                    icp_code=icp,
                    confidence=90,
                    official_company=True,
                    excerpt_id=data["excerpts"][0]["excerpt_id"],
                    industry="Business services",
                    reasoning="The public services fit this actual catalog customer segment.",
                    unknowns=[],
                )
            elif operation == "research":
                value = {
                    "facts": [
                        {
                            "category": category,
                            "statement": quote,
                            "kind": "OBSERVED",
                            "confidence": 90,
                            **citation(quote),
                        }
                        for category, quote in [
                            ("INDUSTRY", service),
                            ("SERVICES", service),
                            ("PAIN_POINT", need),
                            ("SIGNAL", signal),
                        ]
                    ],
                    "people": [
                        {
                            "name": "Casey Sample",
                            "role": "Operations Director",
                            "email": (
                                None
                                if "contact-review" in url
                                else "casey@fixtures.example.org"
                            ),
                            "phone": None,
                            **citation(person),
                        }
                    ],
                    "unknowns": ["Operating scale not established"],
                }
            elif operation == "scoring":
                value = {
                    "criteria": [
                        {
                            "criterion": c,
                            "points": p,
                            "rationale": "Supported by saved synthetic evidence",
                            "evidence": [citation(quote)],
                        }
                        for c, p, quote in [
                            ("icp_fit", 40, service),
                            ("operational_need", 30, need),
                            ("operating_scale", 0, service),
                            ("buying_signals", 10, signal),
                            ("evidence_quality", 5, service),
                        ]
                    ],
                    "unknowns": [],
                }
            elif operation == "matching":
                value = {
                    "matches": [
                        {
                            "product_code": code,
                            "fit": 85,
                            "rationale": "Matches documented catalog capabilities",
                            "evidence": [citation(service)],
                        }
                        for code in data["products"]
                    ]
                }
            elif operation == "drafting":
                value = {
                    "subject": "A conversation about "
                    + (
                        "invoice processing"
                        if "accounting" in url
                        else "transport scheduling"
                    ),
                    "body": "Hello Casey, your public site describes "
                    + service
                    + "\n\nWould a conversation about the documented product capabilities alongside your existing systems be useful?",
                    "evidence": [citation(service)],
                }
            else:
                raise RuntimeError("Unsupported synthetic operation")
        self.record(
            uid,
            "SUCCESS",
            {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200},
        )
        return self.remember(key, value)


def bootstrap():
    path = Path("/fixtures/accounts.json")
    import pwd

    account = pwd.getpwnam("backend")
    os.chown(path.parent, account.pw_uid, account.pw_gid)
    with Session() as db:
        if db.scalar(select(User.id).limit(1)):
            if not path.exists():
                raise RuntimeError(
                    "Existing acceptance DB has no matching fixture manifest"
                )
            print("Existing isolated fixture manifest retained")
            return
        workspaces = [
            Workspace(name="Transport Acceptance"),
            Workspace(name="Accounting Acceptance"),
        ]
        db.add_all(workspaces)
        db.flush()
        accounts = {}
        for role in ("ADMIN", "OPERATOR", "REVIEWER", "VIEWER"):
            email, password = role.lower() + "@example.test", secrets.token_urlsafe(24)
            actor = User(
                email=email, password_hash=hash_password(password), platform_admin=False
            )
            db.add(actor)
            db.flush()
            for w in workspaces:
                db.add(Membership(workspace_id=w.id, user_id=actor.id, role=role))
            accounts[role] = {"email": email, "password": password}
        outsider_password = secrets.token_urlsafe(24)
        outsider = User(
            email="outsider@example.test",
            password_hash=hash_password(outsider_password),
        )
        db.add(outsider)
        db.flush()
        db.add(
            Membership(
                workspace_id=workspaces[1].id, user_id=outsider.id, role="VIEWER"
            )
        )
        accounts["OUTSIDER"] = {"email": outsider.email, "password": outsider_password}
        manifest = {"accounts": accounts, "workspaces": [str(w.id) for w in workspaces]}
        path.write_text(json.dumps(manifest), encoding="utf-8")
        path.chmod(0o600)
        os.chown(path, account.pw_uid, account.pw_gid)
        db.commit()
    print(
        "Created two isolated products and four workspace roles; credentials saved only in private fixture volume"
    )


def main():
    guard()
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["bootstrap", "worker"])
    args = parser.parse_args()
    if args.command == "bootstrap":
        bootstrap()
    else:
        from marketing_backend.worker import main as worker

        with patch("marketing_backend.stages.Providers", SyntheticProviders), patch(
            "marketing_backend.stages.fetch_public", synthetic_fetch
        ):
            worker()


if __name__ == "__main__":
    main()
