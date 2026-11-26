"""Tabela de laudo de calculo tributario.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calculo_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("versao_formato", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("hash_entrada", sa.String(length=64), nullable=False),
        sa.Column("hash_saida", sa.String(length=64), nullable=False),
        sa.Column("hash_laudo", sa.String(length=64), nullable=False),
        sa.Column("data_emissao", sa.Date(), nullable=True),
        sa.Column(
            "regras", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "tabelas", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "entrada", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "saida", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
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
    op.create_index("ix_calculo_audit_tenant_id", "calculo_audit", ["tenant_id"])
    op.create_index("ix_calculo_audit_trace_id", "calculo_audit", ["trace_id"])
    op.create_index("ix_calculo_audit_hash_laudo", "calculo_audit", ["hash_laudo"])
    op.create_index("ix_calculo_audit_tenant_data", "calculo_audit", ["tenant_id", "data_emissao"])


def downgrade() -> None:
    op.drop_index("ix_calculo_audit_tenant_data", table_name="calculo_audit")
    op.drop_index("ix_calculo_audit_hash_laudo", table_name="calculo_audit")
    op.drop_index("ix_calculo_audit_trace_id", table_name="calculo_audit")
    op.drop_index("ix_calculo_audit_tenant_id", table_name="calculo_audit")
    op.drop_table("calculo_audit")
