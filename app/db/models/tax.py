"""Laudo de cálculo tributário persistido (retenção fiscal de 5 anos).

Guarda o **laudo completo**, não só os hashes: um hash prova que algo não mudou, mas
não diz o que era. Em fiscalização é preciso mostrar a entrada, o resultado e as
regras; o hash serve para provar que aquilo não foi editado depois.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, MixinId, MixinTimestamps


class CalculoAudit(Base, MixinId, MixinTimestamps):
    """Rastro auditável de um cálculo tributário."""

    __tablename__ = "calculo_audit"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Documento ao qual o cálculo pertence, quando houver.
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL")
    )

    #: Correlaciona com a emissão e com os logs.
    trace_id: Mapped[str | None] = mapped_column(String(64), index=True)
    versao_formato: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    hash_entrada: Mapped[str] = mapped_column(String(64), nullable=False)
    hash_saida: Mapped[str] = mapped_column(String(64), nullable=False)
    hash_laudo: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    #: Data de emissão do documento: é por ela que se escolhe a tabela vigente.
    data_emissao: Mapped[date | None] = mapped_column(Date)
    #: Regras aplicadas, na ordem em que foram aplicadas.
    regras: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    #: Tabelas consultadas com a versão lida (nome, versao, vigências).
    tabelas: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    #: Entrada e saída completas. É o que se mostra em fiscalização.
    entrada: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    saida: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        # Consulta típica: "os cálculos deste tenant nesta competência".
        Index("ix_calculo_audit_tenant_data", "tenant_id", "data_emissao"),
    )
