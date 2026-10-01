import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_base_url: str
    api_key: str
    session_secret: str
    reviewer_identity: str
    trust_cloudflare_identity: bool

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.getenv("MARKETING_API_KEY", "").strip()
        session_secret = os.getenv("DASHBOARD_SESSION_SECRET", "").strip()

        if not api_key:
            raise RuntimeError("MARKETING_API_KEY is required")
        if not session_secret or session_secret == "CHANGE_ME":
            raise RuntimeError("DASHBOARD_SESSION_SECRET must be configured")

        return cls(
            api_base_url=os.getenv(
                "MARKETING_API_BASE_URL",
                "http://marketing-api:8000",
            ).rstrip("/"),
            api_key=api_key,
            session_secret=session_secret,
            reviewer_identity=os.getenv(
                "DASHBOARD_REVIEWER_IDENTITY",
                "parimala",
            ).strip() or "parimala",
            trust_cloudflare_identity=os.getenv(
                "TRUST_CLOUDFLARE_IDENTITY",
                "false",
            ).lower() in {"1", "true", "yes", "on"},
        )


def icp_options() -> list[dict[str, str]]:
    configured = [
        (
            "Logistics / Haulage",
            os.getenv("ICP_LOGISTICS_HAULAGE_ID", "").strip(),
        ),
        (
            "Passenger Transport",
            os.getenv("ICP_PASSENGER_TRANSPORT_ID", "").strip(),
        ),
        (
            "Commercial / Enterprise Fleet",
            os.getenv("ICP_COMMERCIAL_ENTERPRISE_ID", "").strip(),
        ),
    ]

    return [
        {"label": label, "id": value}
        for label, value in configured
        if value
    ]
