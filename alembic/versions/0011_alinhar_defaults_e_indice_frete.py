"""Alinha o banco aos modelos: defaults e índice único de `frete_credenciais`.

Revision ID: 0011
Revises: 0010

Causa raiz: `alembic check` detectava 8 operações em 3 tabelas.

1. `calculo_audit` (5 colunas) e `dlq.payload` tinham `server_default` no banco, mas os modelos
   declaram apenas `default=` (Python). Fonte de verdade: o modelo. Removemos o default do
   banco — o valor continua sendo aplicado pelo ORM na inserção.

2. `frete_credenciais`: o modelo declara `unique=True, index=True`, que gera um **índice único**
   `ix_frete_credenciais_tenant_id`. O banco tinha uma **constraint única**
   `uq_frete_credenciais_tenant_id` mais um índice não-único de mesmo nome. Alinhamos ao modelo.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

#: Colunas que perderam o `server_default` para casar com `default=` do modelo.
COLUNAS_SEM_DEFAULT: tuple[tuple[str, str], ...] = (
    ("calculo_audit", "versao_formato"),
    ("calculo_audit", "regras"),
    ("calculo_audit", "tabelas"),
    ("calculo_audit", "entrada"),
    ("calculo_audit", "saida"),
    ("dlq", "payload"),
)


def upgrade() -> None:
    for tabela, coluna in COLUNAS_SEM_DEFAULT:
        op.alter_column(tabela, coluna, server_default=None)

    op.drop_constraint("uq_frete_credenciais_tenant_id", "frete_credenciais", type_="unique")
    op.drop_index("ix_frete_credenciais_tenant_id", table_name="frete_credenciais")
    op.create_index(
        "ix_frete_credenciais_tenant_id",
        "frete_credenciais",
        ["tenant_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_frete_credenciais_tenant_id", table_name="frete_credenciais")
    op.create_index(
        "ix_frete_credenciais_tenant_id",
        "frete_credenciais",
        ["tenant_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_frete_credenciais_tenant_id", "frete_credenciais", ["tenant_id"]
    )

    # Restaura os defaults que existiam antes desta migration.
    op.alter_column("dlq", "payload", server_default=sa.text("'{}'::jsonb"))
    op.alter_column("calculo_audit", "saida", server_default=sa.text("'{}'::jsonb"))
    op.alter_column("calculo_audit", "entrada", server_default=sa.text("'{}'::jsonb"))
    op.alter_column("calculo_audit", "tabelas", server_default=sa.text("'[]'::jsonb"))
    op.alter_column("calculo_audit", "regras", server_default=sa.text("'[]'::jsonb"))
    op.alter_column("calculo_audit", "versao_formato", server_default=sa.text("1"))
