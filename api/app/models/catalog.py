from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import Boolean, DateTime, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.workspaces import WorkspaceOwned


class Product(WorkspaceOwned, Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("workspace_id", "code", name="uq_products_workspace_code"),)

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    code: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    category: Mapped[str | None] = mapped_column(Text)

    description: Mapped[str | None] = mapped_column(Text)

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
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


class ICPProfile(WorkspaceOwned, Base):
    __tablename__ = "icp_profiles"
    __table_args__ = (UniqueConstraint("workspace_id", "code", name="uq_icp_profiles_workspace_code"),)

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    code: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(Text)

    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    qualification_rules: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
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
