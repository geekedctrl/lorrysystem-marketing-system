#!/usr/bin/env python3
from __future__ import annotations
import csv
import io
import re
import sys
import uuid
import httpx
from PIL import Image, ImageDraw

BASE_URL = "http://127.0.0.1:8080"
passed = failed = 0

def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"[PASS] {name}" + (f" — {detail}" if detail else ""))
    else:
        failed += 1
        print(f"[FAIL] {name}" + (f" — {detail}" if detail else ""))

def csrf_from(html):
    m = re.search(r'name="csrf"\s+value="([^"]+)"', html)
    if not m:
        raise RuntimeError("CSRF token not found")
    return m.group(1)

def token_from(html):
    m = re.search(r'name="import_token"\s+value="([^"]+)"', html)
    if not m:
        raise RuntimeError("import token not found")
    return m.group(1)

headers = [
    "company_name","website","domain","industry","country","state","city",
    "contact_name","job_title","email","phone","linkedin_url","icp","priority",
]

def make_csv(rows):
    out = io.StringIO(newline="")
    w = csv.writer(out)
    w.writerow(headers)
    w.writerows(rows)
    return out.getvalue().encode()

with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
    r = client.get("/leads/import")
    check("Import page", r.status_code == 200, f"HTTP {r.status_code}")
    csrf = csrf_from(r.text)

    r = client.get("/leads/import/csv/template")
    check("CSV template", r.status_code == 200, f"HTTP {r.status_code}")
    check("Template headers", r.text.splitlines()[0] == ",".join(headers))

    r = client.post(
        "/leads/import/card/extract",
        data={"csrf": csrf},
        files={"file": ("bad.txt", b"x", "text/plain")},
    )
    check("Bad card type rejected", r.status_code == 422, f"HTTP {r.status_code}")

    image = Image.new("RGB", (900, 450), "white")
    d = ImageDraw.Draw(image)
    d.text((40, 60), "Validator Logistics Sdn Bhd", fill="black")
    d.text((40, 130), "validator@example.invalid", fill="black")
    buf = io.BytesIO()
    image.save(buf, "PNG")
    r = client.post(
        "/leads/import/card/extract",
        data={"csrf": csrf},
        files={"file": ("card.png", buf.getvalue(), "image/png")},
    )
    check("Valid card reaches review", r.status_code == 200, f"HTTP {r.status_code}")
    check("Card review editable", 'name="company_name"' in r.text)

    u = uuid.uuid4().hex[:12]
    company = f"Import Validator {u} Sdn Bhd"
    domain = f"import-validator-{u}.example"
    email = f"validator-{u}@example.invalid"
    csv_data = make_csv([[
        company, f"https://{domain}", domain, "Logistics", "MY",
        "Selangor", "Shah Alam", "", "Operations Manager", email,
        "+60123456789", "", "LOGISTICS_HAULAGE", "",
    ]])

    r = client.post(
        "/leads/import/csv/preview",
        data={"csrf": csrf},
        files={"file": ("valid.csv", csv_data, "text/csv")},
    )
    check("CSV preview", r.status_code == 200, f"HTTP {r.status_code}")
    check("Blank priority -> MEDIUM", "MEDIUM" in r.text)
    check("New valid row READY", "READY" in r.text)
    tok = token_from(r.text)

    r = client.post(
        "/leads/import/csv/commit",
        data={"csrf": csrf, "import_token": tok},
    )
    check("CSV commit", r.status_code == 200, f"HTTP {r.status_code}")
    check("One row imported", "Imported</span><strong>1</strong>" in r.text)
    check("Lead DISCOVERED", "Created as DISCOVERED" in r.text)

    r = client.get("/leads/import")
    csrf = csrf_from(r.text)
    r = client.post(
        "/leads/import/csv/preview",
        data={"csrf": csrf},
        files={"file": ("duplicate.csv", csv_data, "text/csv")},
    )
    check("Duplicate preview", r.status_code == 200, f"HTTP {r.status_code}")
    check("Duplicate detected", "DUPLICATE" in r.text)
    tok2 = token_from(r.text)

    r = client.get(f"/leads/import/csv/errors/{tok2}")
    check("Error-row download", r.status_code == 200, f"HTTP {r.status_code}")
    check("Error CSV says DUPLICATE", "DUPLICATE" in r.text)

    bad = make_csv([[
        f"Bad Validator {u}", "", "", "", "MY", "", "", "", "",
        "not-an-email", "", "", "NOT_AN_ICP", "URGENT",
    ]])
    r = client.get("/leads/import")
    csrf = csrf_from(r.text)
    r = client.post(
        "/leads/import/csv/preview",
        data={"csrf": csrf},
        files={"file": ("bad.csv", bad, "text/csv")},
    )
    check("Invalid preview renders", r.status_code == 200, f"HTTP {r.status_code}")
    check("Invalid row detected", "INVALID" in r.text)

print("=" * 64)
print(f"PASS: {passed}")
print(f"FAIL: {failed}")
print("RESULT:", "PASSED" if failed == 0 else "FAILED")
sys.exit(0 if failed == 0 else 1)
