from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


LeadPriority = Literal[
    "LOW",
    "MEDIUM",
    "HIGH",
]


LeadStatus = Literal[
    "DISCOVERED",
    "RESEARCHING",
    "QUALIFIED",
    "READY_FOR_OUTREACH",
    "CONTACTED",
    "REPLIED",
    "CONVERTED",
    "DISQUALIFIED",
    "LOST",
]


class LeadCreate(BaseModel):
    company_id: UUID
    primary_contact_id: UUID | None = None

    # ICP is mandatory for every lead.
    icp_profile_id: UUID

    priority: LeadPriority = "MEDIUM"


LeadClosureReason = Literal[
    "NO_RESPONSE",
    "NOT_INTERESTED",
    "WRONG_FIT",
    "DUPLICATE",
    "OTHER",
]


class LeadStatusUpdate(BaseModel):
    status: LeadStatus
    reason: LeadClosureReason | None = None
    note: str | None = None
    closed_by: str | None = None


class LeadRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID

    company_id: UUID
    primary_contact_id: UUID | None

    # ICP is now guaranteed to exist.
    icp_profile_id: UUID

    status: str
    priority: str
    current_score: int | None

    discovered_at: datetime
    qualified_at: datetime | None
    contacted_at: datetime | None
    converted_at: datetime | None

    created_at: datetime
    updated_at: datetime
