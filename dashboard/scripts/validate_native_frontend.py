"""Offline BFF and real-browser acceptance with synthetic native responses only.

python dashboard/scripts/validate_native_frontend.py [--browser]
No live API, provider, database or outbound requests are made.
"""
import copy
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
import unittest

import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.native import create_app, safe_url

W1 = "11111111-1111-4111-8111-111111111111"
W2 = "22222222-2222-4222-8222-222222222222"
L1 = "33333333-3333-4333-8333-333333333333"
RID = "44444444-4444-4444-8444-444444444444"
AID = "55555555-5555-4555-8555-555555555555"
JID = "66666666-6666-4666-8666-666666666666"
CID = "77777777-7777-4777-8777-777777777777"
SID = "88888888-8888-4888-8888-888888888888"
DID = "99999999-9999-4999-8999-999999999999"
NOW = "2026-10-11T10:00:00Z"


class NativeFixture:
    def __init__(self):
        self.calls = []
        self.candidates = {W1: [{"id":CID,"domain":"candidate.example.com","company_name":"Synthetic Candidate Logistics","website":"https://candidate.example.com/","status":"READY_FOR_REVIEW","industry":"Logistics","confidence":85,"icp_code":"ICP","reasoning":"Supported public transport services fit the customer segment.","source_url":"https://candidate.example.com/","evidence_quote":"Synthetic Candidate Logistics provides transport and freight services.","unknowns":["Buying intent unknown"],"stale":False,"accepted_lead_id":None}], W2: []}
        self.queries = []
        self.enabled = {W1: True, W2: True}
        self.catalog = {wid: [{"id": "catalog", "kind": "PRODUCT", "code": "OFFER", "name": name, "description": "Documented product capabilities", "rules": {}}, {"id": "icp", "kind": "ICP", "code": "ICP", "name": "Business customers", "description": "Source-backed business targeting", "rules": {}}] for wid, name in [(W1, "Fleet operations"), (W2, "Learning platform")]}
        self.status = "PENDING_APPROVAL"
        self.stale = False
        self.fail_activation = False
        self.activation_keys = []
        self.leads = {W1: [{"id": L1, "company_name": "Synthetic Haulage <script>alert(1)</script>", "website": "https://haulage.example.com"}], W2: [{"id": L1, "company_name": "Synthetic Academy", "website": "https://academy.example.com"}]}
        self.quote = "Morgan Lee Operations Director morgan@example.com"
        self.results = {
            "RESEARCH": {"facts": [{"category": "INDUSTRY", "statement": "Publicly documented logistics services", "source_url": "https://haulage.example.com/team", "evidence_quote": self.quote, "confidence": 85, "kind": "OBSERVED"}], "people": [], "unknowns": ["Fleet size is not established"], "pages": [{"source_url": "https://haulage.example.com/team", "text": self.quote}], "coverage": {"pages_attempted": 2, "unavailable_pages": 1}},
            "CONTACT_SEARCH": {"people": [{"name": "Morgan Lee", "role": "Operations Director", "email": "morgan@example.com", "source_url": "https://haulage.example.com/team", "evidence_quote": self.quote, "profiles": [], "profile_candidates": [{"url": "https://www.linkedin.com/in/synthetic-morgan", "platform": "linkedin.com"}]}], "selected_contact": {"name": "Morgan Lee", "role": "Operations Director", "email": "morgan@example.com"}, "unavailable_queries": 2},
            "SCORING": {"score": 75, "relevance": 60, "opportunity": 15, "criteria": [{"criterion": "ICP fit", "points": 40, "rationale": "Supported industry and business activity", "evidence": []}], "unknowns": [], "adjustments": []},
            "MATCHING": {"matches": [{"product_code": "OFFER", "fit": 80, "rationale": "Matches the documented catalog capabilities", "evidence": []}], "selected_product": "OFFER"},
            "DRAFTING": {"subject": "An exploratory conversation", "body": "Hello Morgan,\n\nYour company describes logistics services. Would a short conversation about your operations be relevant? <img src=x onerror=alert(1)>", "recipient": "morgan@example.com", "channel": "EMAIL", "product_code": "OFFER", "status": "PENDING_APPROVAL", "evidence": []},
        }
        self.job_status = "COMPLETED"
        self.fail_lead = False
        self.completed_results = copy.deepcopy(self.results)
        self.revision = None
        self.parent_snapshot = None
        self.senders = {W1: [{"id":SID,"name":"Synthetic SMTP","from_email":"team@example.test","from_name":"Synthetic Team","host":"smtp.example.test","port":587,"security":"STARTTLS","username":"team@example.test","enabled":True,"verified_at":NOW,"created_at":NOW}], W2: []}
        self.deliveries = {W1: [], W2: []}
        self.suppressions = {W1: [], W2: []}
        self.results["DRAFTING"]["evidence"] = [{"source_url":"https://haulage.example.com/team","evidence_quote":self.quote}]
        self.completed_results = copy.deepcopy(self.results)

    def run(self, current=True):
        return {"id": RID, "lead_id": L1, "status": self.status if current else "FAILED", "stop_reason": "SUPPORTED_CONTACT_REQUIRED" if self.status == "NEEDS_REVIEW" and current else None, "results": self.results, "created_at": NOW, "current": current}

    def respond(self, request):
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, path, body))
        self.queries.append((path,dict(request.url.params)))
        role = request.headers.get("Authorization", "Bearer ADMIN").split()[-1]
        if path == "/auth/login":
            if body["password"] == "bad":
                return httpx.Response(401, json={"detail": "Invalid email or password"})
            return httpx.Response(200, json={"token": body["email"].split("@")[0].upper(), "token_type": "bearer"})
        if path == "/auth/logout":
            return httpx.Response(204)
        if path == "/auth/me":
            return httpx.Response(200,json={"id":role,"email":role.lower()+"@example.com","expires_at":"2026-10-12T00:00:00Z","capabilities":{"create_workspace":False},"private_token":"must-not-reach-browser"})
        if path == "/workspaces":
            return httpx.Response(200, json=[{"id": W1, "name": "Fleet product", "role": role}, {"id": W2, "name": "Education product", "role": role}])
        parts = path.split("/")
        wid, suffix = parts[2], "/".join(parts[3:])
        if suffix=="leads/page":
            values=request.url.params
            leads=[{**l,"created_at":NOW,"current_preparation":self.run() if l["id"]==L1 else None,"primary_contact":self.results.get("CONTACT_SEARCH",{}).get("selected_contact")} for l in self.leads[wid] if values.get("q","").lower() in l["company_name"].lower()]
            if values.get("status"):leads=[l for l in leads if l["current_preparation"] and l["current_preparation"]["status"]==values["status"]]
            offset=int(values.get("cursor",0));limit=int(values.get("limit",25))
            return httpx.Response(200,json={"items":leads[offset:offset+limit],"total":len(leads),"limit":limit,"next_cursor":str(offset+limit) if len(leads)>offset+limit else None,"as_of":NOW})
        if suffix.startswith("leads/") and suffix.count("/")==1:
            lead=next((l for l in self.leads[wid] if l["id"]==suffix.split("/")[1]),None)
            return httpx.Response(200,json={**lead,"created_at":NOW,"current_preparation":self.run(),"primary_contact":self.results.get("CONTACT_SEARCH",{}).get("selected_contact")}) if lead else httpx.Response(404,json={"detail":"Lead not found"})
        if suffix=="catalog/all":
            return httpx.Response(200,json=[{**c,"id":c.get("id",c["code"]),"active":c.get("active",True),"version":c.get("version",1)} for c in self.catalog[wid]])
        if suffix.startswith("catalog/") and request.method=="PATCH":
            for c in self.catalog[wid]:
                if c.get("id",c["code"])==suffix.split("/")[1]:c["active"]=body["active"];c["version"]=c.get("version",1)+1
            if not any(c["kind"]=="PRODUCT" and c.get("active",True) for c in self.catalog[wid]):self.enabled[wid]=False
            return httpx.Response(200,json={"id":suffix.split("/")[1],"code":"OFFER","active":body["active"]})
        if suffix == "catalog":
            if request.method == "PUT":
                assert set(body) == {"kind", "code", "name", "description", "rules"}
                self.catalog[wid] = [x for x in self.catalog[wid] if x["code"] != body["code"]] + [body]
                return httpx.Response(201, json={"id": "catalog", "code": body["code"]})
            return httpx.Response(200, json=[c for c in self.catalog[wid] if c.get("active",True)])
        if suffix == "candidates":
            values=dict(request.url.params)
            rows=[c for c in self.candidates[wid] if not values.get("status") or c["status"]==values["status"]]
            offset=int(values.get("offset",0));limit=int(values.get("limit",25))
            return httpx.Response(200,json={"items":rows[offset:offset+limit],"total":len(rows),"offset":offset,"limit":limit})
        if suffix.startswith("candidates/"):
            if request.method == "POST":
                c=self.candidates[wid][0]
                c["status"]="REJECTED" if suffix.endswith("/reject") else "RETRY_PENDING" if suffix.endswith("/retry") else "ACCEPTED"
                if c["status"]=="ACCEPTED":
                    c["accepted_lead_id"]=CID
                    self.leads[wid].append({"id":CID,"company_name":c["company_name"],"website":c["website"]})
                return httpx.Response(200,json={"candidate_id":suffix.split("/")[1],"status":"REJECTED" if suffix.endswith("/reject") else "ACCEPTED"})
            return httpx.Response(404,json={"detail":"Candidate not found"})
        if suffix == "operations":
            return httpx.Response(200, json={"enabled": self.enabled[wid], "preferences": {"product_description": "Actual product with documented capabilities", "batch_size": 3}, "next_discovery_at": None, "stalled_jobs": [], "delayed_pending_jobs": [], "current_preparation": [self.run()], "provider_health": {}, "recent_provider_usage": [], "cost_basis": "Conservative reservations"})
        if suffix == "senders":
            if request.method == "POST":
                assert body["password"] and isinstance(body["port"],int) and isinstance(body["enabled"],bool)
                row={k:v for k,v in body.items() if k!="password"}|{"id":SID,"verified_at":None,"created_at":NOW}
                self.senders[wid].append(row); return httpx.Response(201,json=row)
            return httpx.Response(200,json=self.senders[wid])
        if suffix.startswith("senders/") and suffix.endswith("/verify"):
            self.senders[wid][0]["verified_at"]=NOW
            return httpx.Response(200,json={"verified":True,"verified_at":NOW})
        if suffix == "deliveries":
            if request.method == "POST":
                assert set(body)=={"approval_id","sender_id","idempotency_key"}
                row={"id":DID,"approval_id":body["approval_id"],"sender_id":body["sender_id"],"status":"PENDING_SEND_APPROVAL","snapshot":{"recipient":"morgan@example.com","subject":"An exploratory conversation","body":"Reviewed body"},"requested_by":role,"send_approved_by":None,"send_approved_at":None,"created_at":NOW,"attempts":[]}
                self.deliveries[wid]=[row]; return httpx.Response(201,json=row)
            return httpx.Response(200,json=self.deliveries[wid])
        if suffix.startswith("deliveries/") and suffix.endswith("/approve-send"):
            assert body=={"confirmed":True}; row=self.deliveries[wid][0]; row["status"]="QUEUED"; row["send_approved_by"]=role; row["send_approved_at"]=NOW; row["attempts"]=[{"id":"attempt","number":1,"status":"READY","message_id":"<synthetic@example.test>","failure_code":None,"created_at":NOW,"finished_at":None}]
            return httpx.Response(202,json=row)
        if suffix.startswith("deliveries/") and suffix.endswith("/retry"):
            assert body=={"confirmed":True}; self.deliveries[wid][0]["status"]="QUEUED"; return httpx.Response(202,json=self.deliveries[wid][0])
        if suffix == "email-suppressions":
            if request.method == "POST":
                row={"id":"suppression","created_at":NOW,**body}; self.suppressions[wid].append(row); return httpx.Response(201,json=row)
            return httpx.Response(200,json=self.suppressions[wid])
        if suffix == "leads":
            if request.method == "POST":
                assert set(body) == {"company_name", "website"}
                if self.fail_lead:
                    self.fail_lead = False
                    return httpx.Response(422, json={"detail":[{"loc":["body","website"],"msg":"Use a public company website"}]})
                item = {"id": L1, **body}
                self.leads[wid].append(item)
                return httpx.Response(201, json=item)
            return httpx.Response(200, json=self.leads[wid])
        if suffix == "approvals":
            if self.revision:
                return httpx.Response(200,json=[self.revision,{"id":AID,"run_id":RID,"version":1,"status":"CHANGES_REQUESTED","snapshot":self.parent_snapshot,"stale":True,"decision":{"note":"Please revise the opening"},"created_at":NOW}])
            return httpx.Response(200, json=[] if self.status == "NEEDS_REVIEW" else [{"id": AID, "run_id": RID, "status": "PENDING" if self.status == "PENDING_APPROVAL" else self.status, "snapshot": {"draft": self.results["DRAFTING"], "results": self.results, "inputs": {"company": {"company_name": "Saved synthetic company"}, "catalog": self.catalog[wid]}}, "stale": self.stale, "decision": {}, "created_at": NOW}])
        if suffix.endswith("/revision"):
            assert set(body)=={"idempotency_key","expected_version","subject","body","evidence","note"}
            self.parent_snapshot=copy.deepcopy({"draft":self.results["DRAFTING"],"results":self.results,"inputs":{"company":{"company_name":"Saved synthetic company"},"catalog":self.catalog[wid]}})
            snapshot=copy.deepcopy(self.parent_snapshot)
            snapshot["draft"].update({k:body[k] for k in ["subject","body","evidence"]})
            snapshot["revision"]={"editor_id":role,"version":2,"note":body["note"],"reviewer_note":"Please revise the opening"}
            self.revision={"id":"77777777-7777-4777-8777-777777777777","run_id":RID,"version":2,"status":"PENDING","snapshot":snapshot,"stale":False,"decision":{},"created_at":NOW}
            return httpx.Response(201,json={"approval_id":self.revision["id"],"run_id":RID,"version":2,"status":"PENDING_APPROVAL","sent":False})
        if suffix.endswith("/decision"):
            assert set(body) == {"decision", "note"}
            if self.stale and body["decision"] == "APPROVED":
                return httpx.Response(409, json={"detail": "Draft context is stale"})
            self.status = body["decision"]
            if self.revision:
                if body["decision"]=="APPROVED" and self.revision["snapshot"]["revision"]["editor_id"]==role:return httpx.Response(403,json={"detail":"Another reviewer required"})
                self.revision["status"]=body["decision"]
            return httpx.Response(200, json={"status": self.status, "sent": False})
        if suffix.endswith("/preparation"):
            return httpx.Response(200, json=[self.run(), self.run(False)])
        if suffix.endswith("/prepare"):
            assert set(body) == {"idempotency_key"}
            self.status = "NEEDS_REVIEW"
            self.results = {stage: value for stage,value in self.completed_results.items() if stage in {"RESEARCH","CONTACT_SEARCH"}}
            self.results["CONTACT_SEARCH"] = {**self.results["CONTACT_SEARCH"], "selected_contact": None}
            return httpx.Response(202, json={"run_id": RID})
        if suffix.endswith("/contact"):
            assert set(body).issubset({"person_index", "profile_url", "business_contact"})
            self.status = "PENDING_APPROVAL"
            self.results = copy.deepcopy(self.completed_results)
            return httpx.Response(202, json={"run_id": RID, "status": "PREPARING"})
        if suffix == "jobs":
            return httpx.Response(200, json=[{"id": JID, "workspace_id": wid, "lead_id": L1, "run_id": RID, "managed": True, "kind": "DISCOVERY", "status": self.job_status, "attempts": 1, "max_attempts": 3, "result": {}, "failure_code": None, "history": [], "created_at": NOW, "available_at": NOW, "lease_until": None}])
        if suffix == "automation/activate":
            assert set(body) == {"idempotency_key", "product_description", "target_customers", "country", "language", "brand_voice", "batch_size"}
            assert isinstance(body["batch_size"], int)
            self.activation_keys.append(body["idempotency_key"])
            if self.fail_activation:
                self.fail_activation = False
                return httpx.Response(503, json={"detail": "Synthetic temporary failure"})
            self.enabled[wid] = True
            return httpx.Response(202, json={"job_id": JID, "status": "PENDING"})
        if suffix in {"automation/pause", "automation/resume"}:
            self.enabled[wid] = suffix.endswith("resume")
            return httpx.Response(200, json={"enabled": self.enabled[wid]})
        if suffix == "discovery" or suffix.endswith("/retry") or suffix.endswith("/retry-contact-search"):
            self.job_status = "COMPLETED"
            return httpx.Response(202, json={"job_id": JID, "status": "PENDING"})
        return httpx.Response(404, json={"detail": "Fixture route unavailable"})


class BFFAcceptance(unittest.TestCase):
    def setUp(self):
        self.fixture = NativeFixture()
        self.client = TestClient(create_app(httpx.MockTransport(self.fixture.respond)))

    def sign_in(self, role="admin"):
        response = self.client.post("/session/login", json={"email": role+"@example.com", "password": "synthetic"}, headers={"X-Native-Request": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("HttpOnly",response.headers["set-cookie"])
        self.assertNotIn("token", response.json())
        csrf = self.client.get("/session").json()["csrf"]
        result = self.client.post("/session/workspace", json={"workspace_id": W1}, headers={"X-CSRF-Token": csrf}).json()
        return {"X-CSRF-Token": result["csrf"]}

    def test_opaque_session_and_csrf(self):
        self.assertEqual(self.client.post("/session/login", json={}).status_code, 403)
        headers = self.sign_in()
        self.assertEqual(len(self.client.cookies.get("native_session")),43)
        self.assertNotIn("ADMIN", self.client.cookies.get("native_session"))
        self.assertEqual(self.client.post(f"/gateway/{W1}/discovery", json={"idempotency_key": "synthetic-key"}).status_code, 403)

    def test_native_dashboard_deployment_routes(self):
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/dashboard")
        page = self.client.get("/dashboard")
        self.assertEqual(page.status_code, 200)
        self.assertIn("/static/native.js", page.text)
        self.assertEqual(self.client.get("/health").json(), {"status": "ok", "frontend": "native"})

    def test_switch_rejects_old_workspace_and_csrf(self):
        headers = self.sign_in()
        switch = self.client.post("/session/workspace", headers=headers, json={"workspace_id": W2})
        self.assertEqual(switch.status_code, 200)
        self.assertEqual(self.client.get(f"/gateway/{W1}/leads").status_code, 409)
        self.assertEqual(self.client.post(f"/gateway/{W2}/discovery", headers=headers, json={"idempotency_key": "synthetic-key"}).status_code, 403)
        self.assertEqual(self.client.get(f"/gateway/{W2}/leads").json()[0]["company_name"], "Synthetic Academy")

    def test_role_matrix(self):
        for role, work, setup, review in [("admin",True,True,True),("operator",True,False,False),("reviewer",False,False,True),("viewer",False,False,False)]:
            with self.subTest(role=role):
                headers = self.sign_in(role)
                self.assertEqual(self.client.post(f"/gateway/{W1}/discovery",headers=headers,json={"idempotency_key":"synthetic-key"}).status_code,202 if work else 403)
                self.assertEqual(self.client.post(f"/gateway/{W1}/automation/pause",headers=headers).status_code,200 if setup else 403)
                self.fixture.status="PENDING_APPROVAL"
                self.assertEqual(self.client.post(f"/gateway/{W1}/approvals/{AID}/decision",headers=headers,json={"decision":"APPROVED","note":"Reviewed evidence"}).status_code,200 if review else 403)

    def test_expiry_and_allowlist(self):
        headers = self.sign_in()
        self.assertEqual(self.client.post(f"/gateway/{W1}/sending",headers=headers).status_code,404)
        self.assertEqual(self.client.get(f"/gateway/{W1}/auth/login").status_code,404)
        for session in self.client.app.state.sessions.values():
            session["expires"] = 0
        self.assertEqual(self.client.get("/session").status_code,401)

    def test_stale_approval_and_logout(self):
        headers = self.sign_in()
        self.fixture.stale=True
        self.assertEqual(self.client.post(f"/gateway/{W1}/approvals/{AID}/decision",headers=headers,json={"decision":"APPROVED","note":"Reviewed evidence"}).status_code,409)
        self.assertEqual(self.client.post("/session/logout",headers=headers).status_code,200)
        self.assertEqual(self.client.get(f"/gateway/{W1}/leads").status_code,401)

    def test_source_link_validation(self):
        for source in ["javascript:alert(1)", "http://127.0.0.1/x", "http://10.0.0.1", "https://user:secret@example.com", "http://localhost.local"]:
            self.assertIsNone(safe_url(source))
        self.assertEqual(safe_url("https://company.example.com/team"),"https://company.example.com/team")

    def test_candidate_review_permissions_and_filter_allowlist(self):
        for role in ["admin", "operator", "reviewer", "viewer"]:
            headers=self.sign_in(role)
            response=self.client.get(f"/gateway/{W1}/candidates?status=READY_FOR_REVIEW&limit=25&offset=0")
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()["items"][0]["accepted_lead_id"],None)
            self.assertEqual(self.client.post(f"/gateway/{W1}/candidates/{CID}/accept",headers=headers,json={}).status_code,403 if role=="viewer" else 200)
            self.fixture.candidates[W1][0]["status"]="READY_FOR_REVIEW"
            self.fixture.candidates[W1][0]["accepted_lead_id"]=None
        self.sign_in()
        for query in ["limit=101", "offset=-1", "offset=0&offset=1", "token=private", "cursor=anything"]:
            self.assertEqual(self.client.get(f"/gateway/{W1}/candidates?{query}").status_code,422)

    def test_profile_and_validated_paging(self):
        self.sign_in()
        profile=self.client.get("/session").json()["user"]
        self.assertFalse(profile["capabilities"]["create_workspace"])
        self.assertNotIn("private_token",profile)
        result=self.client.get(f"/gateway/{W1}/leads/page",params={"q":"Synthetic","limit":25,"status":"PENDING_APPROVAL"})
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()["total"],1)
        self.assertEqual(self.fixture.queries[-1][1],{"q":"Synthetic","limit":"25","status":"PENDING_APPROVAL"})
        for query in ["limit=101","limit=bad","status=BAD","secret=bad","q=a&q=b"]:
            self.assertEqual(self.client.get(f"/gateway/{W1}/leads/page?{query}").status_code,422)
        self.assertEqual(self.client.get(f"/gateway/{W1}/leads/{L1}").status_code,200)

    def test_catalog_and_revision_permissions(self):
        for role,allowed in [("admin",True),("operator",False),("reviewer",False),("viewer",False)]:
            headers=self.sign_in(role)
            response=self.client.patch(f"/gateway/{W1}/catalog/catalog",json={"active":False},headers=headers)
            self.assertEqual(response.status_code,200 if allowed else 403)
        headers=self.sign_in("admin")
        self.assertEqual(self.client.patch(f"/gateway/{W1}/catalog/catalog",json={"active":True}).status_code,403)
        self.assertEqual(self.client.get(f"/gateway/{W1}/catalog/all").status_code,200)

    def test_sending_gateway_permissions_redaction_and_separate_approval(self):
        for role in ["admin","operator","reviewer","viewer"]:
            headers=self.sign_in(role)
            senders=self.client.get(f"/gateway/{W1}/senders")
            self.assertEqual(senders.status_code,200)
            self.assertNotIn("password",json.dumps(senders.json()))
            create=self.client.post(f"/gateway/{W1}/deliveries",headers=headers,json={"approval_id":AID,"sender_id":SID,"idempotency_key":"synthetic-delivery-key"})
            self.assertEqual(create.status_code,201 if role in {"admin","operator"} else 403)
            self.fixture.deliveries[W1]=[]
        headers=self.sign_in("admin")
        created=self.client.post(f"/gateway/{W1}/deliveries",headers=headers,json={"approval_id":AID,"sender_id":SID,"idempotency_key":"synthetic-delivery-key"})
        self.assertEqual(created.json()["status"],"PENDING_SEND_APPROVAL")
        approved=self.client.post(f"/gateway/{W1}/deliveries/{DID}/approve-send",headers=headers,json={"confirmed":True})
        self.assertEqual(approved.status_code,202)
        self.assertEqual(approved.json()["status"],"QUEUED")
        self.assertEqual(self.client.get(f"/gateway/{W1}/deliveries?secret=bad").status_code,422)


def browser_acceptance():
    import uvicorn
    from playwright.sync_api import sync_playwright
    fixture=NativeFixture()
    sock=socket.socket();sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(create_app(httpx.MockTransport(fixture.respond)),log_level="error"))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.05)
    output=Path(__file__).resolve().parents[2]/"tmp/native-ui-review";output.mkdir(parents=True,exist_ok=True)
    errors=[]
    try:
        with sync_playwright() as p:
            executable=os.getenv("FRONTEND_BROWSER",r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
            browser=p.chromium.launch(executable_path=executable if Path(executable).exists() else None,headless=True)
            page=browser.new_page(viewport={"width":1440,"height":1000})
            page.set_default_timeout(10000)
            page.on("pageerror",lambda error:errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}")
            page.get_by_label("Email",exact=True).fill("admin@example.com");page.get_by_label("Password").fill("synthetic")
            page.get_by_role("button",name="Sign in",exact=True).click()
            try:
                page.get_by_role("heading",name="Ready for human review").wait_for()
            except Exception:
                print("URL:",page.url);print("Errors:",errors);print("Calls:",fixture.calls)
                raise
            page.screenshot(path=str(output/"overview-desktop.png"),full_page=True)
            original_leads=len(fixture.leads[W1])
            page.get_by_role("link",name="Discovery",exact=True).click()
            page.get_by_role("heading",name="Synthetic Candidate Logistics",exact=True).wait_for()
            assert len(fixture.leads[W1])==original_leads
            page.screenshot(path=str(output/"discovery-candidate-review.png"),full_page=True)
            page.get_by_role("button",name="Accept & start research",exact=True).click()
            page.get_by_text("No candidates in this view.",exact=False).wait_for()
            assert len(fixture.leads[W1])==original_leads+1
            assert fixture.candidates[W1][0]["status"]=="ACCEPTED"
            page.screenshot(path=str(output/"discovery-manual-acceptance.png"),full_page=True)
            page.get_by_role("link",name="Product setup",exact=True).click()
            page.get_by_role("button",name="Pause automation",exact=True).click()
            page.get_by_role("button",name="Resume automation",exact=True).wait_for()
            page.get_by_role("button",name="Resume automation",exact=True).click()
            page.get_by_role("button",name="Pause automation",exact=True).wait_for()
            page.get_by_role("button",name="Deactivate Fleet operations",exact=True).click()
            page.get_by_role("button",name="Reactivate Fleet operations",exact=True).wait_for()
            page.get_by_role("button",name="Reactivate Fleet operations",exact=True).click()
            page.get_by_role("button",name="Resume automation",exact=True).click()
            page.get_by_role("button",name="Pause automation",exact=True).wait_for()
            page.get_by_label("Describe the real product").fill("A real synthetic product with documented operations capabilities")
            page.get_by_role("button",name="Continue",exact=True).click();page.get_by_role("button",name="Continue",exact=True).click()
            fixture.fail_activation=True
            page.get_by_role("button",name="Save offerings & activate").click();page.get_by_text("Synthetic temporary failure",exact=False).wait_for()
            assert page.get_by_role("heading",name="Product setup").count() >= 1
            page.get_by_role("button",name="Save offerings & activate").click();page.get_by_role("heading",name="Jobs & history").wait_for()
            assert fixture.activation_keys[-1]==fixture.activation_keys[-2],"Retry changed the idempotency key"
            page.get_by_role("link",name="Leads",exact=True).click()
            page.get_by_text("Add a company",exact=True).click()
            page.get_by_label("Company name",exact=True).fill("Synthetic new company")
            page.get_by_label("Official public website",exact=True).fill("https://new.example.com")
            fixture.fail_lead=True
            page.get_by_role("button",name="Add company",exact=True).click()
            page.get_by_text("website: Use a public company website",exact=True).wait_for()
            assert page.get_by_label("Company name",exact=True).input_value()=="Synthetic new company"
            page.on("dialog",lambda dialog:dialog.accept())
            page.get_by_role("row").filter(has_text="Synthetic Haulage").get_by_role("button",name="Open lead",exact=True).click()
            page.locator(".lead-hero").get_by_role("heading",name="Synthetic Haulage <script>alert(1)</script>",exact=True).wait_for()
            assert page.get_by_role("navigation",name="Preparation stages").get_by_role("button").count()==5
            assert page.get_by_text("75/100",exact=True).count()==1
            page.screenshot(path=str(output/"lead-profile-desktop.png"),full_page=True)
            page.set_viewport_size({"width":390,"height":844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"),"Lead profile overflows at mobile width"
            page.screenshot(path=str(output/"lead-profile-mobile.png"),full_page=True)
            page.set_viewport_size({"width":1440,"height":1000})
            page.get_by_role("navigation",name="Preparation stages").get_by_role("button",name="Qualification: Complete").click()
            assert page.get_by_role("tab",name="Qualification",exact=True).get_attribute("aria-selected")=="true"
            page.get_by_role("button",name="Start fresh preparation").click()
            page.get_by_role("tab",name="Qualification",exact=True).click()
            page.get_by_text("Qualification has not completed yet.",exact=True).wait_for()
            page.get_by_role("tab",name="People",exact=True).click()
            page.get_by_text("2 contact searches were unavailable.",exact=False).wait_for()
            page.get_by_role("button",name="Choose this contact",exact=True).click()
            page.get_by_role("tab",name="Outreach",exact=True).click();page.get_by_role("heading",name="An exploratory conversation").wait_for()
            assert page.locator("img").count()==0,"Draft HTML was rendered"
            page.screenshot(path=str(output/"lead-outreach-desktop.png"),full_page=True)
            page.get_by_label("Review note (required for every decision)").fill("Reviewed the saved evidence and contact")
            page.get_by_role("button",name="Approve draft",exact=True).click()
            page.get_by_text("Decision saved. No message was sent.",exact=True).wait_for()
            page.get_by_role("link",name="Approvals",exact=True).click()
            page.get_by_role("button",name="Create delivery for send approval",exact=True).click()
            page.get_by_role("button",name="Approve and queue this email",exact=True).click()
            page.get_by_text("Queued",exact=True).wait_for()
            page.get_by_role("link",name="Sending",exact=True).click()
            page.get_by_role("heading",name="Delivery history",exact=True).wait_for()
            page.screenshot(path=str(output/"sending-outbox-synthetic.png"),full_page=True)
            page.get_by_role("link",name="Leads",exact=True).click()
            page.get_by_role("row").filter(has_text="Synthetic Haulage").get_by_role("button",name="Open lead",exact=True).click()
            page.get_by_role("tab",name="Activity",exact=True).click();page.get_by_text("Historical",exact=False).wait_for()
            page.get_by_role("tab",name="Activity",exact=True).focus();page.keyboard.press("Home");assert page.get_by_role("tab",name="Overview",exact=True).get_attribute("aria-selected")=="true"
            fixture.status="PENDING_APPROVAL";fixture.stale=True
            page.get_by_role("link",name="Approvals",exact=True).click();assert page.get_by_role("button",name="Approve draft",exact=True).is_disabled()
            page.locator("#workspace").select_option(W2);page.get_by_role("heading",name="Ready for human review").wait_for();assert "Synthetic Haulage" not in page.locator("#view").inner_text()
            page.get_by_role("link",name="Leads",exact=True).click();page.get_by_text("Synthetic Academy",exact=True).wait_for()
            fixture.job_status="FAILED"
            page.get_by_role("link",name="Activity & operations",exact=True).click()
            page.get_by_role("button",name="Retry failed job",exact=True).click()
            page.get_by_role("button",name="Retry failed job",exact=True).wait_for(state="detached")
            page.get_by_role("link",name="Leads",exact=True).click();page.get_by_text("Synthetic Academy",exact=True).wait_for()
            for width,height,name in [(1024,768,"tablet"),(390,844,"mobile")]:
                page.set_viewport_size({"width":width,"height":height});page.screenshot(path=str(output/f"leads-{name}.png"),full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"),f"Page overflow at {width}"
            page.get_by_role("button",name="Menu",exact=True).click();page.keyboard.press("Escape");assert not page.locator("#sidebar").is_visible()
            page.set_viewport_size({"width":1440,"height":1000})
            page.get_by_role("button",name="Theme:",exact=False).click();page.screenshot(path=str(output/"leads-theme.png"),full_page=True)
            page.get_by_role("button",name="Sign out",exact=True).click();page.get_by_role("heading",name="Welcome back").wait_for()
            for role in ["operator","reviewer","viewer"]:
                page.get_by_label("Email",exact=True).fill(role+"@example.com");page.get_by_label("Password").fill("synthetic");page.get_by_role("button",name="Sign in",exact=True).click();page.get_by_role("heading",name="Ready for human review").wait_for()
                assert page.get_by_role("link",name="Product setup",exact=True).count()==0
                page.get_by_role("link",name="Discovery",exact=True).click()
                page.get_by_role("heading",name="Find your next customers",exact=True).wait_for()
                assert page.get_by_role("button",name="Find leads",exact=True).count()==(1 if role=="operator" else 0)
                page.get_by_role("link",name="Approvals",exact=True).click()
                page.get_by_role("heading",name="Draft review",exact=True).wait_for()
                assert page.get_by_role("button",name="Approve draft",exact=True).count()==(1 if role=="reviewer" else 0)
                page.get_by_role("button",name="Sign out",exact=True).click();page.get_by_role("heading",name="Welcome back").wait_for()
            fixture.stale=False;fixture.status="CHANGES_REQUESTED"
            page.get_by_label("Email",exact=True).fill("admin@example.com");page.get_by_label("Password").fill("synthetic");page.get_by_role("button",name="Sign in",exact=True).click()
            page.get_by_role("heading",name="Ready for human review").wait_for()
            # More than one page; open an older record through direct detail.
            fixture.leads[W1]+=[{"id":f"00000000-0000-4000-8000-{i:012d}","company_name":f"Older company {i}","website":"https://older.example.com"} for i in range(30)]
            page.get_by_role("link",name="Leads",exact=True).click()
            page.get_by_role("button",name="Next page",exact=True).click()
            page.get_by_role("link",name="Older company 29",exact=True).wait_for()
            page.get_by_role("link",name="Older company 29",exact=True).click()
            page.locator(".lead-hero").get_by_role("heading",name="Older company 29",exact=True).wait_for()
            page.get_by_role("link",name="Leads",exact=True).click()
            page.get_by_role("link",name="Older company 29",exact=True).wait_for()
            page.get_by_label("Search companies",exact=True).fill("Older company 29")
            page.get_by_role("button",name="Apply filters",exact=True).click()
            page.get_by_text("1 matching companies",exact=False).wait_for()
            assert page.get_by_role("button",name="Next page",exact=True).is_disabled()
            page.get_by_role("link",name="Approvals",exact=True).click()
            page.get_by_text("Edit requested changes",exact=True).click()
            page.get_by_label("Revised subject",exact=True).fill("A revised sourced opening")
            page.get_by_label("Revision note",exact=True).fill("Updated the opening following review")
            page.get_by_role("button",name="Submit revision for review",exact=True).click()
            page.get_by_text("You edited this version.",exact=False).wait_for()
            assert page.get_by_role("button",name="Approve draft",exact=True).is_disabled()
            assert fixture.parent_snapshot["draft"]["subject"]=="An exploratory conversation"
            page.get_by_role("button",name="Sign out",exact=True).click()
            page.get_by_label("Email",exact=True).fill("reviewer@example.com");page.get_by_label("Password").fill("synthetic");page.get_by_role("button",name="Sign in",exact=True).click()
            page.get_by_role("heading",name="Ready for human review").wait_for()
            page.get_by_role("link",name="Approvals",exact=True).click()
            page.get_by_label("Review note (required for every decision)",exact=True).fill("Reviewed the separate human revision")
            page.get_by_role("button",name="Approve draft",exact=True).click()
            page.get_by_text("Decision saved. No message was sent.",exact=True).wait_for()
            assert not errors,errors
            browser.close()
        print("Browser acceptance passed: setup retry, contact continuation, approval, stale refusal, isolation, roles, responsive layouts, keyboard, escaping and theme.")
        print(f"Screenshots: {output}")
    finally:
        server.should_exit=True;thread.join(timeout=5);sock.close()


if __name__=="__main__":
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(BFFAcceptance)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():sys.exit(1)
    if "--browser" in sys.argv:browser_acceptance()
