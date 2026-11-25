"""Tabelas operacionais: entrega de webhook, lote de importação e apuração.

Estas três tabelas têm em comum serem o registro do trabalho assíncrono: o que
saiu, o que entrou em massa e o que foi apurado por competência.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, MixinId, MixinTimestamps
from app.db.models.enums import (
    ProvedorGuia,
    StatusApuracao,
    StatusLote,
    StatusWebhook,
    coluna_enum,
)


class WebhookDelivery(Base, MixinId, MixinTimestamps):
    """Uma tentativa de entrega de webhook, com assinatura e retentativa.

    O registro é criado **antes** da primeira tentativa. Isso é deliberado: se o
    processo morrer no meio da entrega, existe linha em estado `pending` para o
    worker reencontrar. Webhook não pode depender de memória de processo.
    """

    __tablename__ = "webhook_deliveries"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tipo_evento: Mapped[str] = mapped_column(String(60), nullable=False)
    url_destino: Mapped[str] = mapped_column(String(500), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    #: HMAC-SHA256 do corpo enviado, para o receptor conferir a origem.
    assinatura: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[StatusWebhook] = mapped_column(
        coluna_enum(StatusWebhook, nome="status_webhook"),
        nullable=False,
        default=StatusWebhook.PENDENTE,
        server_default=StatusWebhook.PENDENTE.value,
    )
    tentativas: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    codigo_http: Mapped[int | None] = mapped_column(Integer)
    ultimo_erro: Mapped[str | None] = mapped_column(Text)
    proxima_tentativa: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    entregue_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_webhook_deliveries_tenant_status", "tenant_id", "status"),
        Index("ix_webhook_deliveries_pendentes", "status", "proxima_tentativa"),
    )


class BatchJob(Base, MixinId, MixinTimestamps):
    """Importação em lote (CSV/planilha) com contadores e relatório de falhas."""

    __tablename__ = "batch_jobs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tipo: Mapped[str] = mapped_column(String(40), nullable=False, default="nfse")
    status: Mapped[StatusLote] = mapped_column(
        coluna_enum(StatusLote, nome="status_lote"),
        nullable=False,
        default=StatusLote.PENDENTE,
        server_default=StatusLote.PENDENTE.value,
    )

    nome_arquivo: Mapped[str | None] = mapped_column(String(255))
    total_linhas: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    processadas: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    sucesso: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    falhas: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    #: Lista por linha: {linha, status, invoice_id, erro}.
    relatorio: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    erro: Mapped[str | None] = mapped_column(Text)
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_batch_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_batch_jobs_tenant_created", "tenant_id", "created_at"),
    )


class TaxAssessment(Base, MixinId, MixinTimestamps):
    """Apuração de tributos de uma competência, com a guia correspondente.

    `provedor` existe porque **não há guia nacional única** para NFS-e. MAN/DNA,
    DAS e guia municipal são documentos diferentes, com layouts diferentes e
    regras de validade diferentes. Modelar como um único "DART" seria inventar
    um documento que não existe.
    """

    __tablename__ = "tax_assessments"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    competencia: Mapped[str] = mapped_column(String(7), nullable=False)  # AAAA-MM
    provedor: Mapped[ProvedorGuia] = mapped_column(
        coluna_enum(ProvedorGuia, nome="provedor_guia"),
        nullable=False,
        default=ProvedorGuia.MAN,
        server_default=ProvedorGuia.MAN.value,
    )
    status: Mapped[StatusApuracao] = mapped_column(
        coluna_enum(StatusApuracao, nome="status_apuracao"),
        nullable=False,
        default=StatusApuracao.ABERTA,
        server_default=StatusApuracao.ABERTA.value,
    )

    total_servicos: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    total_iss: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    total_tributos: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    quantidade_documentos: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    guia_numero: Mapped[str | None] = mapped_column(String(60))
    vencimento: Mapped[date | None] = mapped_column(Date)
    linha_digitavel: Mapped[str | None] = mapped_column(String(120))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    erro: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "competencia",
            "provedor",
            name="uq_tax_assessments_tenant_competencia_provedor",
        ),
        Index("ix_tax_assessments_tenant_competencia", "tenant_id", "competencia"),
    )
