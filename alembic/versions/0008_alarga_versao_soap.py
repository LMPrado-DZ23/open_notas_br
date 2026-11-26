"""alarga versao_soap de webservices_sefaz para 8

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-26

DEFEITO CORRIGIDO: a migration 0005 criou `versao_soap` como VARCHAR(4), mas o SQLAlchemy
grava o **nome** do membro do enum (`SOAP_11`, `SOAP_12` — 7 caracteres), não o valor
(`1.1`). Resultado: **qualquer** tentativa de cadastrar endpoint de SEFAZ estourava com
"value too long for type character varying(4)".

Isso significa que "preparar para as SEFAZ de todos os estados" era impossível antes desta
migration — não por falta de dados, mas por largura de coluna. O modelo já tinha `length=8`;
a migration ficou para trás.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "webservices_sefaz",
        "versao_soap",
        existing_type=sa.String(length=4),
        type_=sa.String(length=8),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Só é seguro voltar se nenhum registro usar os nomes de 7 caracteres.
    op.execute(sa.text("DELETE FROM webservices_sefaz WHERE versao_soap NOT IN ('1.1', '1.2')"))
    op.alter_column(
        "webservices_sefaz",
        "versao_soap",
        existing_type=sa.String(length=8),
        type_=sa.String(length=4),
        existing_nullable=False,
    )
