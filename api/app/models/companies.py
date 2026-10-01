from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import (
    Boolean,
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Company(Base):
    __tablename__ = "companies"

    __table_args__ = (
        CheckConstraint(
            "fleet_size_estimate >= 0",
            name="ck_companies_fleet_size_estimate_nonnegative",
        ),
        CheckConstraint(
            "fleet_size_confidence BETWEEN 0 AND 100",
            name="ck_companies_fleet_size_confidence_range",
        ),
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    normalized_name: Mapped[str | None] = mapped_column(Text)
    website_url: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str | None] = mapped_column(CHAR(2))
    state: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    fleet_size_estimate: Mapped[int | None] = mapped_column(Integer)
    fleet_size_confidence: Mapped[int | None] = mapped_column(Integer)
    source_type: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'ACTIVE'"),
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    company_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "companies.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    full_name: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    job_title: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'ACTIVE'"),
    )

    source_url: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


Index(
    "idx_companies_normalized_name",
    Company.normalized_name,
)

Index(
    "idx_companies_domain_unique",
    func.lower(Company.domain),
    unique=True,
    postgresql_where=Company.domain.is_not(None),
)

Index(
    "idx_contacts_company_id",
    Contact.company_id,
)

Index(
    "idx_contacts_email_unique",
    func.lower(Contact.email),
    unique=True,
    postgresql_where=Contact.email.is_not(None),
)
