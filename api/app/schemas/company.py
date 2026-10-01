from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1)

    website_url: str | None = None
    domain: str | None = None
    industry: str | None = None

    country_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
    )

    state: str | None = None
    city: str | None = None

    fleet_size_estimate: int | None = Field(
        default=None,
        ge=0,
    )

    source_type: str | None = None
    source_url: str | None = None

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID

    name: str
    normalized_name: str | None

    website_url: str | None
    domain: str | None
    industry: str | None

    country_code: str | None
    state: str | None
    city: str | None

    fleet_size_estimate: int | None
    fleet_size_confidence: int | None

    source_type: str | None
    source_url: str | None

    status: str

    created_at: datetime
    updated_at: datetime
