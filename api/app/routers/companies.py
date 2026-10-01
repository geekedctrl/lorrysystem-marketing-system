from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.company import (
    CompanyCreate,
    CompanyRead,
)
from app.services.company_service import (
    DuplicateCompanyError,
    create_company,
    get_company,
    list_companies,
)


router = APIRouter(
    prefix="/api/companies",
    tags=["Companies"],
)


@router.post(
    "",
    response_model=CompanyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_company_endpoint(
    data: CompanyCreate,
    db: Session = Depends(get_db),
):
    try:
        return create_company(
            db,
            data,
        )

    except DuplicateCompanyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "match_type": exc.match_type,
                "existing_company_id": str(
                    exc.company.id
                ),
                "existing_company_name": (
                    exc.company.name
                ),
            },
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=list[CompanyRead],
)
def list_companies_endpoint(
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    db: Session = Depends(get_db),
):
    return list_companies(
        db,
        limit,
        offset=offset,
    )


@router.get(
    "/{company_id}",
    response_model=CompanyRead,
)
def get_company_endpoint(
    company_id: UUID,
    db: Session = Depends(get_db),
):
    company = get_company(
        db,
        company_id,
    )

    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )

    return company
