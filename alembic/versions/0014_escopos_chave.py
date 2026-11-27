"""Escopos por chave de API.

Revision ID: 0014
Revises: 0013

Motivo (adendo §4): uma chave "tudo-ou-nada" no tenant impede dar acesso só de leitura ao ERP ou só
de emissão ao PDV. O escopo é por **chave**, não por tenant: o mesmo cliente pode ter várias.

`NULL` significa **sem restrição** — é o que mantém compatibilidade com as chaves já existentes; a
ausência de escopo não pode virar "sem acesso" numa migração.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("api_key_escopos", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "api_key_escopos")
