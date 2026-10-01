from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class ProductRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    code: str
    name: str
    category: str | None
    description: str | None
    active: bool
    created_at: datetime
    updated_at: datetime


class ProductMatchCreate(BaseModel):
    product_id: UUID

    fit_score: int = Field(
        ge=0,
        le=100,
    )

    rationale: str = Field(
        min_length=1,
    )

    @field_validator("rationale")
    @classmethod
    def reject_blank_rationale(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Rationale must not be blank."
            )

        return value


class ProductMatchRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    lead_id: UUID
    product_id: UUID

    fit_score: int
    rationale: str | None

    created_at: datetime
    updated_at: datetime
