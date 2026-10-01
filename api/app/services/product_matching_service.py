from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.catalog import Product
from app.models.leads import (
    Lead,
    ProductMatch,
)
from app.models.marketing import Event
from app.schemas.product_matching import (
    ProductMatchCreate,
)


# ============================================================
# Exceptions
# ============================================================

class ProductMatchingLeadNotFoundError(Exception):
    pass


class ProductNotFoundError(Exception):
    pass


class ProductInactiveError(Exception):
    pass


class ProductMatchingNotAllowedError(Exception):
    pass


class ProductMatchNotFoundError(Exception):
    pass


class ProductMatchingConflictError(Exception):
    pass


# ============================================================
# Rules
# ============================================================

TERMINAL_LEAD_STATUSES = {
    "CONVERTED",
    "DISQUALIFIED",
    "LOST",
}


# ============================================================
# Product Catalog
# ============================================================

def list_products(
    db: Session,
    *,
    active_only: bool = True,
) -> list[Product]:

    statement = select(Product)

    if active_only:
        statement = statement.where(
            Product.active.is_(True)
        )

    statement = statement.order_by(
        Product.code.asc()
    )

    return list(
        db.scalars(statement).all()
    )


def get_product(
    db: Session,
    *,
    product_id: UUID,
) -> Product:

    product = db.get(
        Product,
        product_id,
    )

    if product is None:
        raise ProductNotFoundError(
            "Product not found."
        )

    return product


# ============================================================
# Create / Update Match
# ============================================================

def upsert_product_match(
    db: Session,
    *,
    lead_id: UUID,
    data: ProductMatchCreate,
) -> tuple[ProductMatch, bool]:

    # --------------------------------------------------------
    # 1. Lock the lead.
    #
    # This serializes Product Matching changes for the same
    # lead and prevents concurrent create/update races.
    # --------------------------------------------------------

    lead_statement = (
        select(Lead)
        .where(
            Lead.id == lead_id
        )
        .with_for_update()
    )

    lead = db.scalars(
        lead_statement
    ).first()

    if lead is None:
        raise ProductMatchingLeadNotFoundError(
            "Lead not found."
        )

    # --------------------------------------------------------
    # 2. Terminal leads cannot be matched.
    # --------------------------------------------------------

    if lead.status in TERMINAL_LEAD_STATUSES:
        raise ProductMatchingNotAllowedError(
            f"Lead in {lead.status} status "
            "cannot be product matched."
        )

    # --------------------------------------------------------
    # 3. Product Matching requires Scoring.
    # --------------------------------------------------------

    if lead.current_score is None:
        raise ProductMatchingNotAllowedError(
            "Lead has no current score. "
            "Complete Scoring before Product Matching."
        )

    # --------------------------------------------------------
    # 4. Validate product.
    # --------------------------------------------------------

    product = db.get(
        Product,
        data.product_id,
    )

    if product is None:
        raise ProductNotFoundError(
            "Product not found."
        )

    if not product.active:
        raise ProductInactiveError(
            "Inactive product cannot be matched."
        )

    # --------------------------------------------------------
    # 5. Find existing lead/product match.
    #
    # Existing DB invariant:
    # UNIQUE (lead_id, product_id)
    # --------------------------------------------------------

    match_statement = (
        select(ProductMatch)
        .where(
            ProductMatch.lead_id == lead.id,
            ProductMatch.product_id == product.id,
        )
    )

    product_match = db.scalars(
        match_statement
    ).first()

    now = datetime.now(
        timezone.utc
    )

    created = product_match is None
    previous_fit_score = None

    if created:
        product_match = ProductMatch(
            lead_id=lead.id,
            product_id=product.id,
            fit_score=data.fit_score,
            rationale=data.rationale,
        )

        db.add(product_match)

        event_type = "product_matched"

    else:
        previous_fit_score = (
            product_match.fit_score
        )

        product_match.fit_score = (
            data.fit_score
        )

        product_match.rationale = (
            data.rationale
        )

        product_match.updated_at = now

        event_type = (
            "product_match_updated"
        )

    try:
        # Generate ID for a newly-created ProductMatch before
        # constructing the corresponding Event.
        db.flush()

        event = Event(
            event_type=event_type,
            entity_type="PRODUCT_MATCH",
            entity_id=product_match.id,
            actor_type="API",
            actor_id="marketing-api",
            metadata_json={
                "lead_id": str(
                    lead.id
                ),
                "product_match_id": str(
                    product_match.id
                ),
                "product_id": str(
                    product.id
                ),
                "product_code": (
                    product.code
                ),
                "fit_score": (
                    product_match.fit_score
                ),
                "previous_fit_score": (
                    previous_fit_score
                ),
                "lead_current_score": (
                    lead.current_score
                ),
            },
        )

        db.add(event)

        # ----------------------------------------------------
        # Product Matching intentionally does NOT mutate
        # lead.status.
        #
        # READY_FOR_OUTREACH policy belongs to a later
        # explicitly-approved lifecycle rule.
        # ----------------------------------------------------

        db.commit()
        db.refresh(product_match)

        return (
            product_match,
            created,
        )

    except IntegrityError as exc:
        db.rollback()

        raise ProductMatchingConflictError(
            "Product Match conflicts with "
            "the current matching state."
        ) from exc


# ============================================================
# List Matches
# ============================================================

def list_product_matches_for_lead(
    db: Session,
    *,
    lead_id: UUID,
) -> list[ProductMatch]:

    lead = db.get(
        Lead,
        lead_id,
    )

    if lead is None:
        raise ProductMatchingLeadNotFoundError(
            "Lead not found."
        )

    statement = (
        select(ProductMatch)
        .where(
            ProductMatch.lead_id == lead_id
        )
        .order_by(
            ProductMatch.fit_score.desc(),
            ProductMatch.updated_at.desc(),
        )
    )

    return list(
        db.scalars(statement).all()
    )


# ============================================================
# Match Detail
# ============================================================

def get_product_match(
    db: Session,
    *,
    match_id: UUID,
) -> ProductMatch:

    product_match = db.get(
        ProductMatch,
        match_id,
    )

    if product_match is None:
        raise ProductMatchNotFoundError(
            "Product Match not found."
        )

    return product_match
