"""amplia o CHECK de modelo para 57 (CT-e) e 58 (MDF-e)

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_webservices_sefaz_modelo", "webservices_sefaz", type_="check")
    op.create_check_constraint(
        "ck_webservices_sefaz_modelo",
        "webservices_sefaz",
        "modelo IN ('55','65','57','58')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM webservices_sefaz WHERE modelo IN ('57','58')")
    op.drop_constraint("ck_webservices_sefaz_modelo", "webservices_sefaz", type_="check")
    op.create_check_constraint(
        "ck_webservices_sefaz_modelo", "webservices_sefaz", "modelo IN ('55','65')"
    )
