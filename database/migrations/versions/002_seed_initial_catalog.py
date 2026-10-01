"""seed initial catalog

Revision ID: 002
Revises: 001
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    products = sa.table(
        "products",
        sa.column("code", sa.Text),
        sa.column("name", sa.Text),
    )

    icp_profiles = sa.table(
        "icp_profiles",
        sa.column("code", sa.Text),
        sa.column("name", sa.Text),
    )

    op.bulk_insert(
        products,
        [
            {"code": "TMS", "name": "TMS"},
            {"code": "GPS", "name": "GPS"},
            {"code": "AI_DASHCAM", "name": "AI_DASHCAM"},
            {"code": "DMS", "name": "DMS"},
            {"code": "MDVR", "name": "MDVR"},
            {"code": "FUEL_MONITORING", "name": "FUEL_MONITORING"},
        ],
    )

    op.bulk_insert(
        icp_profiles,
        [
            {
                "code": "LOGISTICS_HAULAGE",
                "name": "LOGISTICS_HAULAGE",
            },
            {
                "code": "PASSENGER_TRANSPORT",
                "name": "PASSENGER_TRANSPORT",
            },
            {
                "code": "COMMERCIAL_ENTERPRISE",
                "name": "COMMERCIAL_ENTERPRISE",
            },
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM icp_profiles
            WHERE code IN (
                'LOGISTICS_HAULAGE',
                'PASSENGER_TRANSPORT',
                'COMMERCIAL_ENTERPRISE'
            )
            """
        )
    )

    op.execute(
        sa.text(
            """
            DELETE FROM products
            WHERE code IN (
                'TMS',
                'GPS',
                'AI_DASHCAM',
                'DMS',
                'MDVR',
                'FUEL_MONITORING'
            )
            """
        )
    )
