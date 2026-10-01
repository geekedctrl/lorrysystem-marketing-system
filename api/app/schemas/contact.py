from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class ContactCreate(BaseModel):
    company_id: UUID

    full_name: str | None = Field(
        default=None,
        min_length=1,
    )

    job_title: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None

    is_primary: bool = False

    source_url: str | None = None

    @model_validator(mode="after")
    def require_meaningful_contact_data(self):
        meaningful_fields = [
            self.full_name,
            self.job_title,
            self.email,
            self.phone,
            self.linkedin_url,
        ]

        if not any(
            value and value.strip()
            for value in meaningful_fields
        ):
            raise ValueError(
                "At least one meaningful contact field is required."
            )

        return self


class ContactRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    company_id: UUID

    full_name: str | None
    job_title: str | None

    email: str | None
    phone: str | None
    linkedin_url: str | None

    is_primary: bool
    status: str

    source_url: str | None

    created_at: datetime
    updated_at: datetime
