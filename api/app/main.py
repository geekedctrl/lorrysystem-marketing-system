
from fastapi import FastAPI

from app.core.config import settings

from app.routers.approvals import (
    router as approvals_router,
)
from app.routers.candidates import (
    router as candidates_router,
)
from app.routers.companies import (
    router as companies_router,
)
from app.routers.contacts import (
    router as contacts_router,
)
from app.routers.health import (
    router as health_router,
)
from app.routers.leads import (
    router as leads_router,
)
from app.routers.marketing_actions import (
    router as marketing_actions_router,
)
from app.routers.research import (
    router as research_router,
)
from app.routers.product_matching import (
    router as product_matching_router,
)
from app.routers.scoring import (
    router as scoring_router,
)

# NEW — F2 External Company Evidence Fetching
from app.routers.public_fetch import (
    router as public_fetch_router,
)

# Existing MVP1 API-key security
from app.security import install_api_key_security
from app.routers.workspaces import router as workspaces_router
from app.routers.discovery_runs import router as discovery_runs_router
from app.routers.pipeline import router as pipeline_router
from app.routers.automation import router as automation_router


# ============================================================
# FastAPI Application
# ============================================================

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)


# ============================================================
# Register Existing API Routers
# ============================================================

app.include_router(health_router)
app.include_router(candidates_router)
app.include_router(approvals_router)
app.include_router(companies_router)
app.include_router(contacts_router)
app.include_router(leads_router)
app.include_router(marketing_actions_router)
app.include_router(research_router)
app.include_router(product_matching_router)
app.include_router(scoring_router)


# ============================================================
# NEW — F2 Public Fetch Router
# ============================================================

app.include_router(public_fetch_router)
app.include_router(workspaces_router)
app.include_router(discovery_runs_router)
app.include_router(pipeline_router)
app.include_router(automation_router)


# ============================================================
# Root Endpoint
# ============================================================

@app.get("/")
def root():
    return {
        "service": settings.app_name,
        "version": "0.1.0",
        "status": "running",
    }


# ============================================================
# Existing MVP1 API-Key Security
# ============================================================

install_api_key_security(app)
