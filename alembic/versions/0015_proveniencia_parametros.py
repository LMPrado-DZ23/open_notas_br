"""Proveniência dos parâmetros oficiais do município.

Revision ID: 0015
Revises: 0014

Motivo (adendo regulatório): `aderente_emissor_nacional` é booleano preenchido à mão e **nunca foi
consultado** por nenhuma decisão de rota (auditoria §77). Sem saber se o valor foi conferido em fonte
oficial, não há como bloquear produção com segurança — e bloquear por padrão quebraria municípios
aderentes cujo campo ficou `False` por omissão.

Estas colunas registram **quem confirmou, quando e onde**. `confirmado_em = NULL` significa
"não consultado", e é isso que separa aviso de bloqueio.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_fiscal_configs",
        sa.Column("aderente_confirmado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenant_fiscal_configs",
        sa.Column("aderente_fonte", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_fiscal_configs", "aderente_fonte")
    op.drop_column("tenant_fiscal_configs", "aderente_confirmado_em")
