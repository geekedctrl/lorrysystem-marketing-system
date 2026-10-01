from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.db.session import engine


router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get("")
def health_check():
    return {
        "status": "ok",
        "service": "lorrysystem-marketing-api",
    }


@router.get("/db")
def database_health_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "ok",
            "database": "reachable",
        }

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )

