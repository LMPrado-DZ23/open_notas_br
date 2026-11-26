"""Fila morta (DLQ): trabalho que falhou e não vai ser retentado sozinho.

Seção 1.3 do v10.0. Guarda o **payload original** porque a alternativa seria pedir ao
cliente para reenviar — e ele não tem mais o estado daquele momento.

`status` separa três coisas que costumam ser confundidas:
- `pendente`: esperando decisão humana
- `reprocessado`: replay executado com sucesso
- `descartado`: analisado e considerado irrecuperável

Guarda `tenant_id` e a consulta filtra por ele: DLQ de um tenant não é visível para
outro, nem para replay.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, MixinId, MixinTimestamps


class StatusDLQ(enum.StrEnum):
    PENDENTE = "pendente"
    REPROCESSADO = "reprocessado"
    DESCARTADO = "descartado"


class ItemDLQ(Base, MixinId, MixinTimestamps):
    """Uma unidade de trabalho que falhou de forma não recuperável automaticamente."""

    __tablename__ = "dlq"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Nome da tarefa/fila de origem (ex.: "emitir_nfse", "webhook").
    fila: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[StatusDLQ] = mapped_column(
        Enum(StatusDLQ, name="status_dlq", native_enum=False, length=16),
        nullable=False,
        default=StatusDLQ.PENDENTE,
        server_default=StatusDLQ.PENDENTE.value,
        index=True,
    )

    #: Payload original. Sem ele, replay seria adivinhação.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    erro: Mapped[str | None] = mapped_column(Text)
    tentativas: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    #: Chave de correlação com a emissão e com os logs.
    trace_id: Mapped[str | None] = mapped_column(String(64), index=True)
    reprocessado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_dlq_tenant_status", "tenant_id", "status"),)

    def __repr__(self) -> str:  # pragma: no cover - diagnóstico
        return f"<ItemDLQ {self.fila} {self.status}>"
