"""Credencial do Melhor Envio por tenant.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frete_credenciais",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("access_token_selado", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_token_selado", sa.LargeBinary(), nullable=True),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escopo", sa.String(length=400), nullable=True),
        sa.Column("sandbox", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("renovado_em", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index("ix_frete_credenciais_tenant_id", "frete_credenciais", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_frete_credenciais_tenant_id", table_name="frete_credenciais")
    op.drop_table("frete_credenciais")
