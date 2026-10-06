from datetime import datetime
from uuid import UUID as PyUUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkspaceOwned:
    workspace_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('workspaces.id', ondelete='RESTRICT'),
        nullable=False, index=True,
    )


class Workspace(Base):
    __tablename__ = 'workspaces'
    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class User(Base):
    __tablename__ = 'users'
    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Membership(Base):
    __tablename__ = 'workspace_memberships'
    __table_args__ = (CheckConstraint("role IN ('ADMIN','OPERATOR','REVIEWER','VIEWER')", name='ck_membership_role'),)
    workspace_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey('workspaces.id', ondelete='RESTRICT'), primary_key=True)
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)


class LoginSession(Base):
    __tablename__ = 'login_sessions'
    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Invitation(Base):
    __tablename__ = 'workspace_invitations'
    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    workspace_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey('workspaces.id', ondelete='RESTRICT'), nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ServiceCredential(Base):
    __tablename__ = 'service_credentials'
    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    workspace_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), ForeignKey('workspaces.id', ondelete='RESTRICT'), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AccessAudit(Base):
    __tablename__ = 'access_audit'
    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text('gen_random_uuid()'))
    workspace_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('workspaces.id', ondelete='RESTRICT'))
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    failures: Mapped[int] = mapped_column(nullable=False, default=0)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
