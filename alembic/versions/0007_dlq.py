"""Tabela de fila morta (DLQ).

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dlq",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fila", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pendente"),
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("reprocessado_em", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_dlq_tenant_id", "dlq", ["tenant_id"])
    op.create_index("ix_dlq_fila", "dlq", ["fila"])
    op.create_index("ix_dlq_status", "dlq", ["status"])
    op.create_index("ix_dlq_trace_id", "dlq", ["trace_id"])
    op.create_index("ix_dlq_tenant_status", "dlq", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_dlq_tenant_status", table_name="dlq")
    op.drop_index("ix_dlq_trace_id", table_name="dlq")
    op.drop_index("ix_dlq_status", table_name="dlq")
    op.drop_index("ix_dlq_fila", table_name="dlq")
    op.drop_index("ix_dlq_tenant_id", table_name="dlq")
    op.drop_table("dlq")
