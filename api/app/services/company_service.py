from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.companies import Company
from app.schemas.company import CompanyCreate


class DuplicateCompanyError(Exception):
    def __init__(
        self,
        match_type: str,
        company: Company,
    ):
        self.match_type = match_type
        self.company = company

        super().__init__(
            f"Company already exists "
            f"(matched by {match_type})."
        )


def normalize_company_name(name: str) -> str:
    return " ".join(
        name.lower().strip().split()
    )


def normalize_domain(
    domain: str | None,
) -> str | None:
    if not domain:
        return None

    value = domain.strip().lower()

    # Support someone accidentally supplying a full URL
    if "://" in value:
        parsed = urlparse(value)
        value = parsed.hostname or value

    value = value.split("/")[0]

    if value.startswith("www."):
        value = value[4:]

    return value.rstrip(".") or None


def domain_from_website(
    website_url: str | None,
) -> str | None:
    if not website_url:
        return None

    value = website_url.strip()

    if not value:
        return None

    if "://" not in value:
        value = f"https://{value}"

    parsed = urlparse(value)

    return normalize_domain(parsed.hostname)


def normalize_website(
    website_url: str | None,
) -> str | None:
    if not website_url:
        return None

    value = website_url.strip()

    if not value:
        return None

    return value.rstrip("/").lower()


def find_duplicate_company(
    db: Session,
    *,
    normalized_name: str,
    domain: str | None,
    website_url: str | None,
) -> tuple[str, Company] | None:

    # 1. Domain — strongest match
    if domain:
        statement = select(Company).where(
            func.lower(Company.domain) == domain.lower()
        )

        company = db.scalars(statement).first()

        if company:
            return "domain", company

    # 2. Normalized company name
    statement = select(Company).where(
        Company.normalized_name == normalized_name
    )

    company = db.scalars(statement).first()

    if company:
        return "normalized_name", company

    # 3. Website
    normalized_site = normalize_website(website_url)

    if normalized_site:
        statement = select(Company).where(
            func.lower(
                func.rtrim(
                    Company.website_url,
                    "/",
                )
            )
            == normalized_site
        )

        company = db.scalars(statement).first()

        if company:
            return "website", company

    return None


def create_company(
    db: Session,
    data: CompanyCreate,
) -> Company:

    normalized_name = normalize_company_name(
        data.name
    )

    # Prefer explicitly supplied domain.
    # Otherwise derive it from website_url.
    domain = normalize_domain(data.domain)

    if not domain:
        domain = domain_from_website(
            data.website_url
        )

    duplicate = find_duplicate_company(
        db,
        normalized_name=normalized_name,
        domain=domain,
        website_url=data.website_url,
    )

    if duplicate:
        match_type, company = duplicate

        raise DuplicateCompanyError(
            match_type,
            company,
        )

    company = Company(
        name=data.name.strip(),
        normalized_name=normalized_name,
        website_url=(
            data.website_url.strip()
            if data.website_url
            else None
        ),
        domain=domain,
        industry=data.industry,
        country_code=(
            data.country_code.upper()
            if data.country_code
            else None
        ),
        state=data.state,
        city=data.city,
        fleet_size_estimate=data.fleet_size_estimate,
        source_type=data.source_type,
        source_url=data.source_url,
        metadata_json=data.metadata,
    )

    db.add(company)

    try:
        db.commit()
        db.refresh(company)

    except IntegrityError as exc:
        db.rollback()

        # Protect against race conditions where another
        # request inserts the same domain simultaneously.
        raise ValueError(
            "Company conflicts with an existing record."
        ) from exc

    return company


def get_company(
    db: Session,
    company_id: UUID,
) -> Company | None:

    return db.get(
        Company,
        company_id,
    )


def list_companies(
    db: Session,
    limit: int = 50,
    offset: int = 0,
) -> list[Company]:

    statement = (
        select(Company)
        .order_by(Company.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    return list(
        db.scalars(statement).all()
    )
