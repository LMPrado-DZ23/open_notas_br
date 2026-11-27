"""Cria `certificado_usos`: auditoria de uso do certificado A1.

Revision ID: 0012
Revises: 0011

Motivo: operar certificado fiscal de terceiros exige responder "quem usou qual A1, quando e para
qual operação". O cofre guardava o certificado, mas não o uso (auditoria §71).

A tabela não guarda segredo nem dado pessoal: `operacao`, `ambiente`, `sucesso` e o **tipo** da
exceção. Mensagem de erro fica de fora porque pode carregar dado do cliente.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "certificado_usos",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("certificado_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("operacao", sa.String(length=40), nullable=False),
        sa.Column("ambiente", sa.String(length=20), nullable=True),
        sa.Column("sucesso", sa.Boolean(), nullable=False),
        sa.Column("erro_tipo", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["certificado_id"], ["tenant_certificates.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_certificado_usos_tenant_id", "certificado_usos", ["tenant_id"])
    op.create_index("ix_certificado_usos_certificado_id", "certificado_usos", ["certificado_id"])
    op.create_index(
        "ix_certificado_usos_tenant_criado", "certificado_usos", ["tenant_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_certificado_usos_tenant_criado", table_name="certificado_usos")
    op.drop_index("ix_certificado_usos_certificado_id", table_name="certificado_usos")
    op.drop_index("ix_certificado_usos_tenant_id", table_name="certificado_usos")
    op.drop_table("certificado_usos")
