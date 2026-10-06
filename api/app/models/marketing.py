from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.workspaces import WorkspaceOwned


class MarketingAction(WorkspaceOwned, Base):
    __tablename__ = "marketing_actions"

    __table_args__ = (
        CheckConstraint(
            "channel IN ("
            "'EMAIL', "
            "'LINKEDIN', "
            "'FACEBOOK', "
            "'INSTAGRAM', "
            "'X'"
            ")",
            name="ck_marketing_actions_channel",
        ),
        CheckConstraint(
            "action_type IN ("
            "'EMAIL', "
            "'FOLLOW_UP', "
            "'POST', "
            "'COMMENT', "
            "'DIRECT_MESSAGE'"
            ")",
            name="ck_marketing_actions_action_type",
        ),
        CheckConstraint(
            "status IN ("
            "'DRAFT', "
            "'PENDING_APPROVAL', "
            "'APPROVED', "
            "'QUEUED', "
            "'SENT', "
            "'PUBLISHED', "
            "'REJECTED', "
            "'FAILED', "
            "'CANCELLED'"
            ")",
            name="ck_marketing_actions_status",
        ),
        CheckConstraint(
            "("
            "channel = 'EMAIL' "
            "AND action_type IN ('EMAIL', 'FOLLOW_UP')"
            ") OR ("
            "channel = 'LINKEDIN' "
            "AND action_type IN "
            "('POST', 'COMMENT', 'DIRECT_MESSAGE')"
            ") OR ("
            "channel IN "
            "('FACEBOOK', 'INSTAGRAM', 'X') "
            "AND action_type = 'POST'"
            ")",
            name=(
                "ck_marketing_actions_"
                "channel_action_pair"
            ),
        ),
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    lead_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "leads.id",
            ondelete="SET NULL",
        ),
    )

    contact_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "contacts.id",
            ondelete="SET NULL",
        ),
    )

    channel: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    action_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    subject: Mapped[str | None] = mapped_column(Text)

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'DRAFT'"),
    )

    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    external_reference: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(Text)

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


class ApprovalRequest(WorkspaceOwned, Base):
    __tablename__ = "approval_requests"

    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'PENDING', "
            "'APPROVED', "
            "'REJECTED', "
            "'CHANGES_REQUESTED'"
            ")",
            name="ck_approval_requests_status",
        ),
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    marketing_action_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "marketing_actions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'PENDING'"),
    )

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    decided_by: Mapped[str | None] = mapped_column(Text)

    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    reviewer_notes: Mapped[str | None] = mapped_column(Text)

    content_snapshot: Mapped[dict[str, Any]] = mapped_column(
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


class Event(WorkspaceOwned, Base):
    __tablename__ = "events"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    event_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    entity_type: Mapped[str | None] = mapped_column(Text)

    entity_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True)
    )

    actor_type: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[str | None] = mapped_column(Text)

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


Index(
    "idx_marketing_actions_status",
    MarketingAction.status,
)

Index(
    "idx_marketing_actions_lead",
    MarketingAction.lead_id,
)

Index(
    "idx_approval_requests_status",
    ApprovalRequest.status,
)

Index(
    "idx_approval_requests_action",
    ApprovalRequest.marketing_action_id,
)

Index(
    "idx_approval_requests_requested_at",
    ApprovalRequest.requested_at,
)

Index(
    "idx_approval_requests_one_pending",
    ApprovalRequest.marketing_action_id,
    unique=True,
    postgresql_where=text(
        "status = 'PENDING'"
    ),
)

Index(
    "idx_events_created_at",
    Event.created_at.desc(),
)

Index(
    "idx_events_event_type",
    Event.event_type,
)
