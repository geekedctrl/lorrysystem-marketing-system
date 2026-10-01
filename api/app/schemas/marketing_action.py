from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    field_validator,
)


MarketingChannel = Literal[
    "EMAIL",
    "LINKEDIN",
    "FACEBOOK",
    "INSTAGRAM",
    "X",
]

MarketingActionType = Literal[
    "EMAIL",
    "FOLLOW_UP",
    "POST",
    "COMMENT",
    "DIRECT_MESSAGE",
]

MarketingActionStatus = Literal[
    "DRAFT",
    "PENDING_APPROVAL",
    "APPROVED",
    "QUEUED",
    "SENT",
    "PUBLISHED",
    "REJECTED",
    "FAILED",
    "CANCELLED",
]


def validate_future_timestamp(
    value: datetime | None,
) -> datetime | None:
    if value is None:
        return None

    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            "scheduled_at must include a timezone."
        )

    if value <= datetime.now(timezone.utc):
        raise ValueError(
            "scheduled_at must be in the future."
        )

    return value


class MarketingActionCreate(BaseModel):
    contact_id: UUID | None = None

    channel: MarketingChannel
    action_type: MarketingActionType

    subject: str | None = None
    content: str

    scheduled_at: datetime | None = None
    created_by: str | None = None

    @field_validator("content")
    @classmethod
    def validate_content(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Content must not be blank."
            )

        return value

    @field_validator("subject")
    @classmethod
    def normalize_subject(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator("created_by")
    @classmethod
    def normalize_created_by(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator("scheduled_at")
    @classmethod
    def scheduled_at_is_future(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        return validate_future_timestamp(
            value
        )


class MarketingActionUpdate(BaseModel):
    contact_id: UUID | None = None
    subject: str | None = None
    content: str | None = None
    scheduled_at: datetime | None = None

    @field_validator("content")
    @classmethod
    def validate_content(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "Content must not be blank."
            )

        return value

    @field_validator("subject")
    @classmethod
    def normalize_subject(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @field_validator("scheduled_at")
    @classmethod
    def scheduled_at_is_future(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        return validate_future_timestamp(
            value
        )


class MarketingActionRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID

    lead_id: UUID | None
    contact_id: UUID | None

    channel: MarketingChannel
    action_type: MarketingActionType

    subject: str | None
    content: str
    status: MarketingActionStatus

    scheduled_at: datetime | None
    executed_at: datetime | None

    external_reference: str | None
    created_by: str | None

    created_at: datetime
    updated_at: datetime
