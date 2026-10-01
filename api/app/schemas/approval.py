from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    field_validator,
)


ApprovalStatus = Literal[
    "PENDING",
    "APPROVED",
    "REJECTED",
    "CHANGES_REQUESTED",
]


class ApprovalDecision(BaseModel):
    decided_by: str
    reviewer_notes: str | None = None

    @field_validator("decided_by")
    @classmethod
    def validate_decided_by(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "decided_by must not be blank."
            )

        return value

    @field_validator("reviewer_notes")
    @classmethod
    def normalize_notes(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None


class ApprovalReject(BaseModel):
    decided_by: str
    reviewer_notes: str

    @field_validator("decided_by")
    @classmethod
    def validate_decided_by(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "decided_by must not be blank."
            )

        return value

    @field_validator("reviewer_notes")
    @classmethod
    def validate_notes(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "reviewer_notes must not be blank."
            )

        return value


class ApprovalRequestChanges(BaseModel):
    decided_by: str
    reviewer_notes: str

    @field_validator("decided_by")
    @classmethod
    def validate_decided_by(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "decided_by must not be blank."
            )

        return value

    @field_validator("reviewer_notes")
    @classmethod
    def validate_notes(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "reviewer_notes must not be blank."
            )

        return value


class ApprovalRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    marketing_action_id: UUID

    status: ApprovalStatus

    requested_at: datetime

    decided_by: str | None
    decided_at: datetime | None
    reviewer_notes: str | None

    content_snapshot: dict[str, Any]

    created_at: datetime
    updated_at: datetime

    marketing_action_status: str
