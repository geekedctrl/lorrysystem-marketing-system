from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

LORRYSYSTEM_WORKSPACE_ID = UUID('00000000-0000-0000-0000-000000000001')


@dataclass(frozen=True)
class Principal:
    workspace_id: UUID
    actor: str
    role: str
    user_id: UUID | None = None


current_principal: ContextVar[Principal | None] = ContextVar('principal', default=None)
