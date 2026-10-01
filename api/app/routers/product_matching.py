from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.product_matching import (
    ProductMatchCreate,
    ProductMatchRead,
    ProductRead,
)
from app.services.product_matching_service import (
    ProductInactiveError,
    ProductMatchNotFoundError,
    ProductMatchingConflictError,
    ProductMatchingLeadNotFoundError,
    ProductMatchingNotAllowedError,
    ProductNotFoundError,
    get_product,
    get_product_match,
    list_product_matches_for_lead,
    list_products,
    upsert_product_match,
)


router = APIRouter(
    tags=["Product Matching"],
)


# ============================================================
# Product Catalog
# ============================================================

@router.get(
    "/api/products",
    response_model=list[ProductRead],
)
def list_products_endpoint(
    active_only: bool = True,
    db: Session = Depends(get_db),
):
    return list_products(
        db,
        active_only=active_only,
    )


@router.get(
    "/api/products/{product_id}",
    response_model=ProductRead,
)
def get_product_endpoint(
    product_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return get_product(
            db,
            product_id=product_id,
        )

    except ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ============================================================
# Product Matching
# ============================================================

@router.post(
    "/api/leads/{lead_id}/product-matches",
    response_model=ProductMatchRead,
)
def upsert_product_match_endpoint(
    lead_id: UUID,
    data: ProductMatchCreate,
    response: Response,
    db: Session = Depends(get_db),
):
    try:
        (
            product_match,
            created,
        ) = upsert_product_match(
            db,
            lead_id=lead_id,
            data=data,
        )

        response.status_code = (
            status.HTTP_201_CREATED
            if created
            else status.HTTP_200_OK
        )

        return product_match

    except ProductMatchingLeadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ProductInactiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except ProductMatchingNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except ProductMatchingConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/api/leads/{lead_id}/product-matches",
    response_model=list[ProductMatchRead],
)
def list_product_matches_endpoint(
    lead_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return list_product_matches_for_lead(
            db,
            lead_id=lead_id,
        )

    except ProductMatchingLeadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/api/product-matches/{match_id}",
    response_model=ProductMatchRead,
)
def get_product_match_endpoint(
    match_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return get_product_match(
            db,
            match_id=match_id,
        )

    except ProductMatchNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
