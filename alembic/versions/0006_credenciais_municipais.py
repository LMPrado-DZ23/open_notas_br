"""Tabela de credenciais municipais por tenant.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credenciais_municipais",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "codigo_ibge",
            sa.String(length=7),
            sa.ForeignKey("municipios_nfse.codigo_ibge"),
            nullable=False,
        ),
        sa.Column("inscricao_municipal", sa.String(length=20), nullable=True),
        sa.Column("usuario_ws_criptografado", sa.LargeBinary(), nullable=True),
        sa.Column("senha_ws_criptografada", sa.LargeBinary(), nullable=True),
        sa.Column("token_ws_criptografado", sa.LargeBinary(), nullable=True),
        sa.Column("serie_rps_padrao", sa.String(length=5), nullable=False, server_default="1"),
        sa.Column("ultimo_numero_rps", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.UniqueConstraint(
            "tenant_id", "codigo_ibge", name="uq_credenciais_municipais_tenant_ibge"
        ),
    )
    op.create_index("ix_credenciais_municipais_tenant_id", "credenciais_municipais", ["tenant_id"])
    op.create_index(
        "ix_credenciais_municipais_codigo_ibge", "credenciais_municipais", ["codigo_ibge"]
    )


def downgrade() -> None:
    op.drop_index("ix_credenciais_municipais_codigo_ibge", table_name="credenciais_municipais")
    op.drop_index("ix_credenciais_municipais_tenant_id", table_name="credenciais_municipais")
    op.drop_table("credenciais_municipais")
