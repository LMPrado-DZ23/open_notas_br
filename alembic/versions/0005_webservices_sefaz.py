"""Tabela de endpoints de webservice da SEFAZ.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webservices_sefaz",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("uf", sa.String(length=2), nullable=False),
        sa.Column("ambiente", sa.String(length=1), nullable=False),
        sa.Column("servico", sa.String(length=32), nullable=False),
        sa.Column("url", sa.String(length=512), nullable=False),
        sa.Column("versao_soap", sa.String(length=4), nullable=False, server_default="1.2"),
        sa.Column("versao_layout", sa.String(length=16), nullable=True),
        sa.Column("fonte_url", sa.String(length=512), nullable=False),
        sa.Column("autorizador", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("uf", "ambiente", "servico", name="uq_webservices_sefaz_endpoint"),
        sa.CheckConstraint("ambiente IN ('1','2')", name="ck_webservices_sefaz_ambiente"),
        sa.CheckConstraint("url LIKE 'https://%'", name="ck_webservices_sefaz_url_https"),
        sa.CheckConstraint("fonte_url LIKE 'https://%'", name="ck_webservices_sefaz_fonte_https"),
    )
    op.create_index("ix_webservices_sefaz_uf", "webservices_sefaz", ["uf"])
    op.create_index("ix_webservices_sefaz_servico", "webservices_sefaz", ["servico"])


def downgrade() -> None:
    op.drop_index("ix_webservices_sefaz_servico", table_name="webservices_sefaz")
    op.drop_index("ix_webservices_sefaz_uf", table_name="webservices_sefaz")
    op.drop_table("webservices_sefaz")
