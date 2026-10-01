from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class ScoreCreate(BaseModel):
    total_score: int = Field(
        ge=0,
        le=100,
    )

    score_breakdown: dict[str, Any]

    scoring_version: str = Field(
        min_length=1,
    )

    rationale: str = Field(
        min_length=1,
    )

    @field_validator(
        "scoring_version",
        "rationale",
    )
    @classmethod
    def reject_blank_strings(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Value must not be blank."
            )

        return value


class ScoreRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    lead_id: UUID

    total_score: int
    score_breakdown: dict[str, Any]

    scoring_version: str
    rationale: str | None

    is_current: bool
    created_at: datetime
