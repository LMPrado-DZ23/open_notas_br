"""adiciona modelo (55/65) e recompoe a chave unica de webservices_sefaz

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-26

MOTIVO (medido em data/fontes/): NF-e (55) e NFC-e (65) usam o mesmo nome de serviço, mas
em algumas UFs o host é diferente. São Paulo:

    55 -> https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx
    65 -> https://homologacao.nfce.fazenda.sp.gov.br/ws/NFeAutorizacao4.asmx

Com a chave antiga `(uf, ambiente, servico)`, cadastrar NFC-e **sobrescreveria** o endpoint
de NF-e e a nota de SP iria para o host errado — falha silenciosa, com recusa só no
autorizador. A chave passa a ser `(uf, modelo, ambiente, servico)`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "webservices_sefaz",
        sa.Column("modelo", sa.String(length=2), nullable=False, server_default="55"),
    )

    op.drop_constraint("uq_webservices_sefaz_endpoint", "webservices_sefaz", type_="unique")
    op.create_unique_constraint(
        "uq_webservices_sefaz_endpoint",
        "webservices_sefaz",
        ["uf", "modelo", "ambiente", "servico"],
    )
    op.create_check_constraint(
        "ck_webservices_sefaz_modelo", "webservices_sefaz", "modelo IN ('55','65')"
    )


def downgrade() -> None:
    # A volta perde a distinção 55/65. Para não deixar a chave antiga violada, mantém só
    # um registro por (uf, ambiente, servico) — o de modelo 55, que é o padrão histórico.
    op.execute(
        sa.text(
            "DELETE FROM webservices_sefaz w USING webservices_sefaz o "
            "WHERE w.uf = o.uf AND w.ambiente = o.ambiente AND w.servico = o.servico "
            "AND w.modelo = '65'"
        )
    )
    op.drop_constraint("ck_webservices_sefaz_modelo", "webservices_sefaz", type_="check")
    op.drop_constraint("uq_webservices_sefaz_endpoint", "webservices_sefaz", type_="unique")
    op.create_unique_constraint(
        "uq_webservices_sefaz_endpoint", "webservices_sefaz", ["uf", "ambiente", "servico"]
    )
    op.drop_column("webservices_sefaz", "modelo")
