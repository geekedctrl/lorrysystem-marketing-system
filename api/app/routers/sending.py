import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from sqlalchemy import select
from app.db.session import get_db
from app.models.sending import SenderAccount, DeliveryAttempt, EmailSuppression
from app.services.smtp_delivery import (
    permit_sender,
    encrypt_password,
    decrypt_password,
    smtp_handoff,
    HandoffError,
    send_approved,
    attempt_read,
)

router = APIRouter(tags=["Controlled email sending"])


def normalized_email(value):
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(
        r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}",
        value,
    ):
        raise ValueError("Enter one business email address without display names")
    return value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SenderWrite(Strict):
    name: str = Field(min_length=2, max_length=120)
    from_email: str = Field(max_length=254)
    from_name: str = Field(min_length=2, max_length=120)
    host: str = Field(
        min_length=3, max_length=253, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]$"
    )
    port: Literal[465, 587] = 587
    security: Literal["TLS", "STARTTLS"] = "STARTTLS"
    username: str = Field(min_length=1, max_length=254)
    password: SecretStr | None = None
    enabled: bool = False

    @field_validator("from_email")
    @classmethod
    def email(cls, value):
        return normalized_email(value)

    @field_validator("name", "from_name", "username")
    @classmethod
    def single_line(cls, value):
        if re.search(r"[\x00-\x1f\x7f]", value):
            raise ValueError("Use a single line")
        return value

    @model_validator(mode="after")
    def connection(self):
        if (self.security, self.port) not in (("TLS", 465), ("STARTTLS", 587)):
            raise ValueError("Use TLS on 465 or STARTTLS on 587")
        if (
            self.password is not None
            and not 1 <= len(self.password.get_secret_value()) <= 4000
        ):
            raise ValueError("SMTP password length is invalid")
        return self


class SendRequest(Strict):
    sender_id: UUID
    idempotency_key: UUID
    confirmed: Literal[True]


class SuppressRequest(Strict):
    email: str = Field(max_length=254)
    reason: Literal["OPT_OUT", "BOUNCE", "DO_NOT_CONTACT"]

    @field_validator("email")
    @classmethod
    def address(cls, value):
        return normalized_email(value)


def sender_read(sender):
    return {
        key: getattr(sender, key)
        for key in (
            "id",
            "name",
            "from_email",
            "from_name",
            "host",
            "port",
            "security",
            "username",
            "enabled",
            "verified_at",
        )
    }


@router.get("/api/senders")
def list_senders(db=Depends(get_db)):
    return [
        sender_read(row)
        for row in db.scalars(select(SenderAccount).order_by(SenderAccount.created_at))
    ]


@router.post("/api/senders", status_code=201)
def create_sender(data: SenderWrite, db=Depends(get_db)):
    principal = permit_sender(admin=True)
    if data.password is None:
        raise HTTPException(422, "Provide an SMTP password")
    row = SenderAccount(
        **data.model_dump(exclude={"password"}),
        password_ciphertext=encrypt_password(
            data.password.get_secret_value(), principal.workspace_id
        )
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return sender_read(row)


@router.put("/api/senders/{sender_id}")
def update_sender(sender_id: UUID, data: SenderWrite, db=Depends(get_db)):
    principal = permit_sender(admin=True)
    row = db.scalar(
        select(SenderAccount).where(SenderAccount.id == sender_id).with_for_update()
    )
    if not row:
        raise HTTPException(404, "Sender account not found")
    if db.scalar(
        select(DeliveryAttempt.id).where(
            DeliveryAttempt.sender_id == row.id, DeliveryAttempt.status == "SENDING"
        )
    ):
        raise HTTPException(
            409, "This sender has an unresolved handoff; check delivery before editing"
        )
    for key, value in data.model_dump(exclude={"password"}).items():
        setattr(row, key, value)
    if data.password is not None:
        row.password_ciphertext = encrypt_password(
            data.password.get_secret_value(), principal.workspace_id
        )
    row.verified_at = None
    db.commit()
    return sender_read(row)


@router.post("/api/senders/{sender_id}/verify")
def verify_sender(sender_id: UUID, db=Depends(get_db)):
    permit_sender(admin=True)
    row = db.scalar(
        select(SenderAccount).where(SenderAccount.id == sender_id).with_for_update()
    )
    if not row:
        raise HTTPException(404, "Sender account not found")
    try:
        smtp_handoff(row, decrypt_password(row))
    except HandoffError as error:
        row.verified_at = None
        db.commit()
        return {"verified": False, "failure_reason": error.code}
    row.verified_at = datetime.now(timezone.utc)
    db.commit()
    return {"verified": True, "verified_at": row.verified_at}


@router.post("/api/actions/{action_id}/send")
def send_email(action_id: UUID, data: SendRequest, db=Depends(get_db)):
    return send_approved(db, action_id, data.sender_id, data.idempotency_key)


@router.get("/api/actions/{action_id}/delivery")
def delivery(action_id: UUID, db=Depends(get_db)):
    row = db.scalar(
        select(DeliveryAttempt).where(DeliveryAttempt.action_id == action_id)
    )
    return attempt_read(row) if row else None


@router.get("/api/email-suppressions")
def suppressions(db=Depends(get_db)):
    return [
        {"id": row.id, "email": row.email, "reason": row.reason}
        for row in db.scalars(
            select(EmailSuppression)
            .order_by(EmailSuppression.created_at.desc())
            .limit(100)
        )
    ]


@router.post("/api/email-suppressions", status_code=201)
def suppress(data: SuppressRequest, db=Depends(get_db)):
    permit_sender()
    row = db.scalar(
        select(EmailSuppression).where(EmailSuppression.email == data.email)
    )
    if not row:
        row = EmailSuppression(**data.model_dump())
        db.add(row)
    else:
        row.reason = data.reason
    db.commit()
    return {"id": row.id, "email": row.email, "reason": row.reason}
