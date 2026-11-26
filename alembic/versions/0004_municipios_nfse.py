"""Tabela de municipios para NFS-e multi-prefeitura.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "municipios_nfse",
        sa.Column("codigo_ibge", sa.String(length=7), primary_key=True),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("uf", sa.String(length=2), nullable=False),
        sa.Column("provedor", sa.String(length=24), nullable=False),
        sa.Column("versao_layout", sa.String(length=16), nullable=True),
        sa.Column("url_homologacao", sa.String(length=512), nullable=True),
        sa.Column("url_producao", sa.String(length=512), nullable=True),
        sa.Column("namespace_xml", sa.String(length=512), nullable=True),
        sa.Column(
            "exige_credencial_municipal",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("assina_rps", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("assina_lote", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("encoding", sa.String(length=12), nullable=False, server_default="UTF-8"),
        sa.Column("homologado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fonte_url", sa.String(length=512), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("codigo_ibge ~ '^[0-9]{7}$'", name="ck_municipios_nfse_ibge_7_digitos"),
        sa.CheckConstraint("uf ~ '^[A-Z]{2}$'", name="ck_municipios_nfse_uf_2_letras"),
        sa.CheckConstraint(
            "url_homologacao IS NULL OR url_homologacao LIKE 'https://%'",
            name="ck_municipios_nfse_homolog_https",
        ),
        sa.CheckConstraint(
            "url_producao IS NULL OR url_producao LIKE 'https://%'",
            name="ck_municipios_nfse_producao_https",
        ),
        sa.CheckConstraint("fonte_url LIKE 'https://%'", name="ck_municipios_nfse_fonte_https"),
    )
    op.create_index("ix_municipios_nfse_uf", "municipios_nfse", ["uf"])
    op.create_index("ix_municipios_nfse_provedor", "municipios_nfse", ["provedor"])


def downgrade() -> None:
    op.drop_index("ix_municipios_nfse_provedor", table_name="municipios_nfse")
    op.drop_index("ix_municipios_nfse_uf", table_name="municipios_nfse")
    op.drop_table("municipios_nfse")
