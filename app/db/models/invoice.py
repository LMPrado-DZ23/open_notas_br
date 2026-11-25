"""Fatura, documento fiscal e evento.

Separar `Invoice` (a intenção de negócio: cobrar por um serviço) de
`FiscalDocument` (o documento fiscal que existe ou não) resolve três problemas:

- idempotência fica na fatura, que é o que o parceiro reenvia;
- uma fatura pode gerar mais de um documento (reenvio, substituição, nota de
  correção), sem perder o vínculo;
- o XML autorizado é imutável e mora no documento, não na fatura.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, MixinId, MixinTimestamps
from app.db.models.enums import (
    AmbienteFiscal,
    OrigemFatura,
    StatusFatura,
    TipoDocumento,
    coluna_enum,
)


class Invoice(Base, MixinId, MixinTimestamps):
    """Intenção de emitir documento fiscal para um serviço prestado."""

    __tablename__ = "invoices"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    #: Chave de idempotência por tenant. Reenvio do parceiro devolve a mesma
    #: fatura em vez de criar nota duplicada.
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    status: Mapped[StatusFatura] = mapped_column(
        coluna_enum(StatusFatura, nome="status_fatura"),
        nullable=False,
        default=StatusFatura.PENDENTE,
        server_default=StatusFatura.PENDENTE.value,
    )
    tipo_documento: Mapped[TipoDocumento] = mapped_column(
        coluna_enum(TipoDocumento, nome="tipo_documento"),
        nullable=False,
        default=TipoDocumento.NFSE,
        server_default=TipoDocumento.NFSE.value,
    )
    origem: Mapped[OrigemFatura] = mapped_column(
        coluna_enum(OrigemFatura, nome="origem_fatura"),
        nullable=False,
        default=OrigemFatura.API,
        server_default=OrigemFatura.API.value,
    )
    ambiente: Mapped[AmbienteFiscal] = mapped_column(
        coluna_enum(AmbienteFiscal, nome="ambiente_fatura"),
        nullable=False,
        default=AmbienteFiscal.HOMOLOGACAO,
        server_default=AmbienteFiscal.HOMOLOGACAO.value,
    )

    valor_servico: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    valor_desconto: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0.00"), server_default=text("0")
    )
    descricao_servico: Mapped[str] = mapped_column(Text, nullable=False)
    competencia: Mapped[str | None] = mapped_column(String(7))  # AAAA-MM

    # Documento do tomador: aceita CNPJ alfanumérico, então sem CHECK numérico.
    tomador_documento: Mapped[str | None] = mapped_column(String(20))
    tomador_nome: Mapped[str | None] = mapped_column(String(200))
    tomador_email: Mapped[str | None] = mapped_column(String(255))

    #: Identificador no sistema de origem (id da venda no DZ23, do atendimento no
    #: Brizu). Serve para reconciliar, não para deduplicar — deduplicar é papel da
    #: `idempotency_key`.
    referencia_externa: Mapped[str | None] = mapped_column(String(255))

    #: Carga completa recebida, preservada para auditoria e reprocessamento.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    erro: Mapped[str | None] = mapped_column(Text)
    processada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    documentos: Mapped[list[FiscalDocument]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", lazy="selectin"
    )
    eventos: Mapped[list[InvoiceEvent]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_invoices_tenant_idempotency_key"),
        Index("ix_invoices_tenant_status", "tenant_id", "status"),
        Index("ix_invoices_tenant_referencia", "tenant_id", "referencia_externa"),
        Index("ix_invoices_tenant_competencia", "tenant_id", "competencia"),
    )


class FiscalDocument(Base, MixinId, MixinTimestamps):
    """Documento fiscal efetivamente gerado e/ou autorizado."""

    __tablename__ = "fiscal_documents"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        index=True,
    )

    tipo_documento: Mapped[TipoDocumento] = mapped_column(
        coluna_enum(TipoDocumento, nome="tipo_documento_fiscal"),
        nullable=False,
        default=TipoDocumento.NFSE,
        server_default=TipoDocumento.NFSE.value,
    )
    ambiente: Mapped[AmbienteFiscal] = mapped_column(
        coluna_enum(AmbienteFiscal, nome="ambiente_documento"),
        nullable=False,
        default=AmbienteFiscal.HOMOLOGACAO,
        server_default=AmbienteFiscal.HOMOLOGACAO.value,
    )

    #: Chave de acesso. NF-e/CT-e têm 44 dígitos; a NFS-e nacional usa outro
    #: identificador (o Id da DPS tem 45 posições). Por isso a coluna é texto
    #: largo e o tipo é que define a validação — nunca um CHECK de 44 dígitos.
    chave: Mapped[str | None] = mapped_column(String(60))
    numero: Mapped[str | None] = mapped_column(String(20))
    serie: Mapped[str | None] = mapped_column(String(5))
    protocolo: Mapped[str | None] = mapped_column(String(60))

    #: `cStat`/código de retorno do provedor, quando houver.
    codigo_status: Mapped[str | None] = mapped_column(String(10))
    mensagem_status: Mapped[str | None] = mapped_column(String(500))

    xml_assinado: Mapped[str | None] = mapped_column(Text)
    xml_autorizado: Mapped[str | None] = mapped_column(Text)
    resposta_bruta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    emitido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    invoice: Mapped[Invoice | None] = relationship(back_populates="documentos")

    __table_args__ = (
        UniqueConstraint("tenant_id", "chave", name="uq_fiscal_documents_tenant_chave"),
        Index("ix_fiscal_documents_tenant_tipo", "tenant_id", "tipo_documento"),
        Index("ix_fiscal_documents_tenant_emitido", "tenant_id", "emitido_em"),
    )


class InvoiceEvent(Base, MixinId):
    """Trilha de eventos da fatura: emissão, rejeição, cancelamento, webhook.

    Funciona como log de auditoria consultável. Guarda requisição e resposta
    porque, em disputa fiscal, o que existia no momento da chamada importa.
    """

    __tablename__ = "invoice_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fiscal_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("fiscal_documents.id", ondelete="SET NULL"),
    )

    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    sequencia: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    status: Mapped[str | None] = mapped_column(String(40))
    mensagem: Mapped[str | None] = mapped_column(Text)
    xml_evento: Mapped[str | None] = mapped_column(Text)
    requisicao: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    resposta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    invoice: Mapped[Invoice] = relationship(back_populates="eventos")

    __table_args__ = (
        Index("ix_invoice_events_tenant_tipo", "tenant_id", "tipo"),
        Index("ix_invoice_events_tenant_created", "tenant_id", "created_at"),
    )
