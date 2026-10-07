from datetime import datetime
from uuid import UUID as PyUUID
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.workspaces import WorkspaceOwned


class SenderAccount(WorkspaceOwned, Base):
    __tablename__ = "sender_accounts"
    __table_args__ = (
        CheckConstraint("security IN ('STARTTLS','TLS')", name="ck_sender_security"),
        CheckConstraint("port IN (465,587)", name="ck_sender_port"),
    )
    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text)
    from_email: Mapped[str] = mapped_column(Text)
    from_name: Mapped[str] = mapped_column(Text)
    host: Mapped[str] = mapped_column(Text)
    port: Mapped[int] = mapped_column(Integer)
    security: Mapped[str] = mapped_column(Text)
    username: Mapped[str] = mapped_column(Text)
    password_ciphertext: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DeliveryAttempt(WorkspaceOwned, Base):
    __tablename__ = "delivery_attempts"
    __table_args__ = (
        UniqueConstraint("action_id"),
        UniqueConstraint("workspace_id", "idempotency_key"),
        CheckConstraint(
            "status IN ('SENDING','ACCEPTED','FAILED','UNCERTAIN')",
            name="ck_delivery_status",
        ),
    )
    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    action_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketing_actions.id")
    )
    sender_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sender_accounts.id")
    )
    idempotency_key: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True))
    recipient: Mapped[str] = mapped_column(Text)
    message_id: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="SENDING")
    failure_reason: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    requested_by: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailSuppression(WorkspaceOwned, Base):
    __tablename__ = "email_suppressions"
    __table_args__ = (UniqueConstraint("workspace_id", "email"),)
    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
