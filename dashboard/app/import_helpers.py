from __future__ import annotations

import csv
import io
import json
import re
import secrets
import time
from pathlib import Path
from typing import Any

from PIL import Image
import pytesseract

CSV_HEADERS = [
    "company_name",
    "website",
    "domain",
    "industry",
    "country",
    "state",
    "city",
    "contact_name",
    "job_title",
    "email",
    "phone",
    "linkedin_url",
    "icp",
    "priority",
]

ICP_CODES = {
    "LOGISTICS_HAULAGE",
    "PASSENGER_TRANSPORT",
    "COMMERCIAL_ENTERPRISE",
}
PRIORITIES = {"LOW", "MEDIUM", "HIGH"}
ACTIVE_LEAD_STATUSES = {
    "DISCOVERED",
    "RESEARCHING",
    "QUALIFIED",
    "READY_FOR_OUTREACH",
    "CONTACTED",
    "REPLIED",
}

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
EMAIL_FIND_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
URL_FIND_RE = re.compile(r"(?:https?://)?(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s]*)?", re.I)
PHONE_FIND_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")

IMPORT_DIR = Path("/tmp/lorrysystem-dashboard-imports")
IMPORT_DIR.mkdir(parents=True, exist_ok=True)


def normalize_company_name(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    suffixes = {
        "sdn", "bhd", "berhad", "private", "limited", "ltd",
        "plc", "inc", "incorporated", "company", "co",
    }
    parts = [p for p in value.split() if p not in suffixes]
    return " ".join(parts)


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def csv_template_text() -> str:
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(CSV_HEADERS)
    writer.writerow([
        "ABC Logistics Sdn Bhd",
        "https://abc.com",
        "abc.com",
        "Logistics",
        "Malaysia",
        "Selangor",
        "Klang",
        "John Tan",
        "Operations Manager",
        "john@abc.com",
        "+60123456789",
        "",
        "LOGISTICS_HAULAGE",
        "HIGH",
    ])
    writer.writerow([
        "Mega Transport",
        "",
        "",
        "",
        "Malaysia",
        "Selangor",
        "Klang",
        "",
        "",
        "",
        "",
        "",
        "LOGISTICS_HAULAGE",
        "",
    ])
    return out.getvalue()


def error_rows_csv(rows: list[dict[str, Any]]) -> str:
    """Return non-READY preview rows as a downloadable CSV."""
    out = io.StringIO(newline="")
    fieldnames = CSV_HEADERS + ["result", "messages"]
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()

    for row in rows:
        if row.get("result") == "READY":
            continue
        messages = [
            *[clean_text(value) for value in row.get("errors", [])],
            *[clean_text(value) for value in row.get("warnings", [])],
        ]
        writer.writerow(
            {
                **{header: clean_text(row.get(header)) for header in CSV_HEADERS},
                "result": clean_text(row.get("result")),
                "messages": " | ".join(value for value in messages if value),
            }
        )

    return out.getvalue()


def parse_csv_bytes(data: bytes, max_rows: int = 5000) -> list[dict[str, str]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must use UTF-8 encoding.") from exc

    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    if set(headers) != set(CSV_HEADERS) or len(headers) != len(CSV_HEADERS):
        missing = [h for h in CSV_HEADERS if h not in headers]
        extra = [h for h in headers if h not in CSV_HEADERS]
        parts = ["CSV headers do not match the required template."]
        if missing:
            parts.append("Missing: " + ", ".join(missing))
        if extra:
            parts.append("Unexpected: " + ", ".join(extra))
        raise ValueError(" ".join(parts))

    rows: list[dict[str, str]] = []
    for index, raw in enumerate(reader, start=2):
        if index - 1 > max_rows:
            raise ValueError(f"CSV exceeds the {max_rows:,} row limit.")
        if not any(clean_text(v) for v in raw.values()):
            continue
        row = {h: clean_text(raw.get(h)) for h in CSV_HEADERS}
        row["_csv_row"] = str(index)
        rows.append(row)
    return rows


def match_company(
    row: dict[str, str],
    companies: list[dict[str, Any]],
) -> tuple[str, dict[str, Any] | None]:
    domain = row.get("domain", "").lower().strip()
    website = row.get("website", "").lower().rstrip("/")
    exact_name = row.get("company_name", "").lower().strip()
    normalized = normalize_company_name(row.get("company_name"))

    exact: list[dict[str, Any]] = []
    fuzzy: list[dict[str, Any]] = []

    for company in companies:
        c_domain = clean_text(company.get("domain")).lower()
        c_web = clean_text(company.get("website_url")).lower().rstrip("/")
        c_name = clean_text(company.get("name")).lower()
        c_norm = normalize_company_name(company.get("name"))

        if domain and c_domain and domain == c_domain:
            exact.append(company)
            continue
        if website and c_web and website == c_web:
            exact.append(company)
            continue
        if exact_name and c_name and exact_name == c_name:
            exact.append(company)
            continue
        if normalized and c_norm and normalized == c_norm:
            fuzzy.append(company)

    unique_exact = {c["id"]: c for c in exact}
    if len(unique_exact) == 1:
        return "EXACT", next(iter(unique_exact.values()))
    if len(unique_exact) > 1:
        return "AMBIGUOUS", None

    unique_fuzzy = {c["id"]: c for c in fuzzy}
    if len(unique_fuzzy) == 1:
        return "AMBIGUOUS", next(iter(unique_fuzzy.values()))
    if len(unique_fuzzy) > 1:
        return "AMBIGUOUS", None
    return "NEW", None


def country_to_code(value: str | None) -> str:
    value = clean_text(value)
    if not value:
        return ""
    common = {
        "malaysia": "MY",
        "singapore": "SG",
        "indonesia": "ID",
        "thailand": "TH",
        "vietnam": "VN",
        "philippines": "PH",
        "brunei": "BN",
    }
    lower = value.lower()
    if lower in common:
        return common[lower]
    if len(value) == 2 and value.isalpha():
        return value.upper()
    return ""


def validate_csv_rows(
    rows: list[dict[str, str]],
    companies: list[dict[str, Any]],
    leads: list[dict[str, Any]],
    icp_code_to_id: dict[str, str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    active_by_company_icp = {
        (lead.get("company_id"), lead.get("icp_profile_id"))
        for lead in leads
        if lead.get("status") in ACTIVE_LEAD_STATUSES
    }

    for row in rows:
        item: dict[str, Any] = dict(row)
        errors: list[str] = []
        warnings: list[str] = []

        if not row["company_name"]:
            errors.append("company_name is required")

        icp_code = row["icp"].upper()
        if not icp_code:
            errors.append("icp is required")
        elif icp_code not in ICP_CODES:
            errors.append("invalid ICP code")
        elif not icp_code_to_id.get(icp_code):
            errors.append("ICP is not configured on the dashboard server")
        item["icp"] = icp_code

        priority = (row["priority"] or "MEDIUM").upper()
        if priority not in PRIORITIES:
            errors.append("priority must be LOW, MEDIUM, or HIGH")
        item["priority"] = priority

        if row["email"] and not EMAIL_RE.match(row["email"]):
            errors.append("invalid email format")

        if row["country"]:
            country_code = country_to_code(row["country"])
            if not country_code:
                warnings.append("country must be a 2-letter code or a supported country name")
            item["country_code"] = country_code
        else:
            item["country_code"] = ""

        match_type, company = match_company(row, companies)
        item["company_match"] = match_type
        item["existing_company_id"] = company.get("id") if company else None
        item["existing_company_name"] = company.get("name") if company else None

        if match_type == "AMBIGUOUS":
            warnings.append("possible existing company match needs review")

        is_duplicate = False
        if company and icp_code_to_id.get(icp_code):
            is_duplicate = (
                company["id"], icp_code_to_id[icp_code]
            ) in active_by_company_icp
        item["duplicate_active_lead"] = is_duplicate

        if errors:
            status = "INVALID"
        elif is_duplicate:
            status = "DUPLICATE"
        elif warnings:
            status = "NEEDS_REVIEW"
        else:
            status = "READY"

        item["result"] = status
        item["errors"] = errors
        item["warnings"] = warnings
        result.append(item)

    return result


def save_import(rows: list[dict[str, Any]]) -> str:
    token = secrets.token_urlsafe(24)
    payload = {
        "created_at": time.time(),
        "rows": rows,
    }
    (IMPORT_DIR / f"{token}.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return token


def load_import(token: str, max_age_seconds: int = 3600) -> list[dict[str, Any]]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,80}", token):
        raise ValueError("Invalid import token.")
    path = IMPORT_DIR / f"{token}.json"
    if not path.exists():
        raise ValueError("Import preview has expired or does not exist.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if time.time() - float(payload.get("created_at", 0)) > max_age_seconds:
        path.unlink(missing_ok=True)
        raise ValueError("Import preview has expired. Please upload the CSV again.")
    return payload.get("rows", [])


def delete_import(token: str) -> None:
    if re.fullmatch(r"[A-Za-z0-9_-]{20,80}", token):
        (IMPORT_DIR / f"{token}.json").unlink(missing_ok=True)


def extract_business_card(image_bytes: bytes) -> dict[str, str]:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    text = pytesseract.image_to_string(image)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    emails = EMAIL_FIND_RE.findall(text)
    urls = URL_FIND_RE.findall(text)
    phones = PHONE_FIND_RE.findall(text)

    linkedin_url = ""
    website = ""
    for url in urls:
        normalized = url if url.lower().startswith(("http://", "https://")) else "https://" + url
        if "linkedin.com" in normalized.lower():
            linkedin_url = linkedin_url or normalized
        elif not EMAIL_FIND_RE.search(url):
            website = website or normalized

    email = emails[0] if emails else ""
    phone = re.sub(r"\s+", " ", phones[0]).strip() if phones else ""

    domain = ""
    if website:
        domain = re.sub(r"^https?://", "", website, flags=re.I)
        domain = re.sub(r"^www\.", "", domain, flags=re.I).split("/")[0]
    elif email and "@" in email:
        domain = email.split("@", 1)[1]

    company_keywords = (
        "sdn", "bhd", "berhad", "logistics", "transport", "transportation",
        "enterprise", "enterprises", "services", "solutions", "systems",
        "technology", "technologies", "group", "company", "co.", "ltd",
    )
    title_keywords = (
        "manager", "director", "executive", "officer", "sales", "marketing",
        "operations", "operation", "engineer", "founder", "ceo", "owner",
        "supervisor", "consultant", "coordinator", "head", "president",
    )

    company_name = ""
    job_title = ""
    for line in lines:
        lower = line.lower()
        if not company_name and any(k in lower for k in company_keywords):
            company_name = line
        if not job_title and any(k in lower for k in title_keywords):
            job_title = line

    noise_fragments = [email.lower(), phone.lower(), domain.lower(), "www.", "http", "@"]
    contact_name = ""
    for line in lines:
        lower = line.lower()
        if line == company_name or line == job_title:
            continue
        if any(fragment and fragment in lower for fragment in noise_fragments):
            continue
        if any(ch.isdigit() for ch in line):
            continue
        words = line.split()
        if 1 < len(words) <= 5 and len(line) <= 60:
            contact_name = line
            break

    if not company_name:
        candidates = [
            line for line in lines
            if line != contact_name
            and line != job_title
            and "@" not in line
            and not any(ch.isdigit() for ch in line)
        ]
        company_name = candidates[-1] if candidates else ""

    return {
        "raw_text": text,
        "company_name": company_name,
        "website": website,
        "domain": domain,
        "industry": "",
        "country": "MY",
        "state": "",
        "city": "",
        "contact_name": contact_name,
        "job_title": job_title,
        "email": email,
        "phone": phone,
        "linkedin_url": linkedin_url,
    }
