from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.companies import Company, Contact
from app.schemas.contact import ContactCreate


class CompanyNotFoundError(Exception):
    pass


class DuplicateContactError(Exception):
    def __init__(
        self,
        match_type: str,
        contact: Contact,
    ):
        self.match_type = match_type
        self.contact = contact

        super().__init__(
            f"Contact already exists "
            f"(matched by {match_type})."
        )


def normalize_email(
    email: str | None,
) -> str | None:
    if not email:
        return None

    value = email.strip().lower()

    return value or None


def clean_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()

    return cleaned or None


def find_contact_by_email(
    db: Session,
    email: str,
) -> Contact | None:

    statement = select(Contact).where(
        func.lower(Contact.email)
        == email.lower()
    )

    return db.scalars(statement).first()


def create_contact(
    db: Session,
    data: ContactCreate,
) -> Contact:

    company = db.get(
        Company,
        data.company_id,
    )

    if company is None:
        raise CompanyNotFoundError(
            "Company not found."
        )

    email = normalize_email(data.email)

    # The database already has a case-insensitive
    # unique email index. Pre-checking gives a
    # friendlier API response.
    if email:
        existing = find_contact_by_email(
            db,
            email,
        )

        if existing:
            raise DuplicateContactError(
                "email",
                existing,
            )

    contact = Contact(
        company_id=data.company_id,
        full_name=(
            data.full_name.strip()
            if data.full_name
            else None
        ),
        job_title=clean_optional_text(
            data.job_title
        ),
        email=email,
        phone=clean_optional_text(
            data.phone
        ),
        linkedin_url=clean_optional_text(
            data.linkedin_url
        ),
        is_primary=data.is_primary,
        source_url=clean_optional_text(
            data.source_url
        ),
    )

    db.add(contact)

    try:
        db.commit()
        db.refresh(contact)

    except IntegrityError as exc:
        db.rollback()

        raise ValueError(
            "Contact conflicts with an existing record."
        ) from exc

    return contact


def get_contact(
    db: Session,
    contact_id: UUID,
) -> Contact | None:

    return db.get(
        Contact,
        contact_id,
    )


def list_contacts(
    db: Session,
    *,
    company_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Contact]:

    statement = select(Contact)

    if company_id is not None:
        statement = statement.where(
            Contact.company_id == company_id
        )

    statement = (
        statement
        .order_by(Contact.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    return list(
        db.scalars(statement).all()
    )
