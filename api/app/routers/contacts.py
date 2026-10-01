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
from app.schemas.contact import (
    ContactCreate,
    ContactRead,
)
from app.services.contact_service import (
    CompanyNotFoundError,
    DuplicateContactError,
    create_contact,
    get_contact,
    list_contacts,
)


router = APIRouter(
    prefix="/api/contacts",
    tags=["Contacts"],
)


@router.post(
    "",
    response_model=ContactRead,
    status_code=status.HTTP_201_CREATED,
)
def create_contact_endpoint(
    data: ContactCreate,
    db: Session = Depends(get_db),
):
    try:
        return create_contact(
            db,
            data,
        )

    except CompanyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except DuplicateContactError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "match_type": exc.match_type,
                "existing_contact_id": str(
                    exc.contact.id
                ),
                "existing_company_id": str(
                    exc.contact.company_id
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
    response_model=list[ContactRead],
)
def list_contacts_endpoint(
    company_id: UUID | None = None,
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
    return list_contacts(
        db,
        company_id=company_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{contact_id}",
    response_model=ContactRead,
)
def get_contact_endpoint(
    contact_id: UUID,
    db: Session = Depends(get_db),
):
    contact = get_contact(
        db,
        contact_id,
    )

    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found.",
        )

    return contact
