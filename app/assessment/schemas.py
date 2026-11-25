"""Contratos de apuração e guia."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import AmbienteFiscal, ProvedorGuia, StatusApuracao


class ApuracaoIn(BaseModel):
    """Pedido de consolidação de uma competência."""

    competencia: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}$",
        description="AAAA-MM. Só documentos autorizados na competência entram.",
        examples=["2026-11"],
    )
    provedor: ProvedorGuia = ProvedorGuia.MAN
    ambiente: AmbienteFiscal = AmbienteFiscal.HOMOLOGACAO


class GuiaOut(BaseModel):
    """Guia gerada pelo provedor."""

    provedor: str
    numero: str
    vencimento: date
    valor: str
    linha_digitavel: str | None = None
    observacao: str | None = None
    dados: dict = Field(default_factory=dict)


class ApuracaoOut(BaseModel):
    """Apuração consolidada."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    competencia: str
    provedor: ProvedorGuia
    status: StatusApuracao
    total_servicos: str
    total_iss: str
    total_tributos: str
    quantidade_documentos: int
    guia_numero: str | None = None
    vencimento: date | None = None
    linha_digitavel: str | None = None
    erro: str | None = None
    created_at: datetime
    updated_at: datetime


class ApuracaoDetalheOut(ApuracaoOut):
    """Apuração com o payload de auditoria (avisos, alíquota usada, faturas)."""

    payload: dict | None = None
