"""Expiração e revogação da API key do tenant.

Revision ID: 0013
Revises: 0012

Motivo (adendo §4/§5): chave sem validade e sem revogação não sustenta operação de credencial de
terceiro. Sem `api_key_revogada_em` não há como matar uma chave vazada sem depender de rotação, e
rotação pressupõe que o dono ainda consiga autenticar.

`api_key_hash` continua único: revogar grava um hash aleatório inutilizável no lugar do anterior, de
modo que a chave revogada deixa de casar em qualquer busca — inclusive na do próprio dono.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("api_key_expira_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("api_key_revogada_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "api_key_revogada_em")
    op.drop_column("tenants", "api_key_expira_em")
