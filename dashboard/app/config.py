import os
from dataclasses import dataclass

from .workspace_context import request_icps


@dataclass(frozen=True)
class Settings:
    api_base_url: str
    session_secret: str

    @classmethod
    def from_env(cls) -> "Settings":
        session_secret = os.getenv("DASHBOARD_SESSION_SECRET", "").strip()
        if not session_secret or session_secret == "CHANGE_ME":
            raise RuntimeError("DASHBOARD_SESSION_SECRET must be configured")
        return cls(
            api_base_url=os.getenv("MARKETING_API_BASE_URL", "http://marketing-api:8000").rstrip("/"),
            session_secret=session_secret,
        )


def icp_options() -> list[dict[str, str]]:
    return request_icps.get()
