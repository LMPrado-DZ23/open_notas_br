"""Contratos de certificado expostos pela API.

Nenhum campo aqui carrega material de chave. O PFX sobe, é selado e nunca mais
sai — nem em upload, nem em listagem, nem em erro.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CertificadoOut(BaseModel):
    """Metadados do certificado. Sem PFX, sem senha, sem chave privada."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    apelido: str
    cnpj: str | None = None
    subject_cn: str | None = None
    emissor: str | None = None
    numero_serie: str | None = None
    valido_de: datetime | None = None
    valido_ate: datetime | None = None
    fingerprint_sha256: str | None = None
    ativo: bool
    created_at: datetime

    #: Calculado, não persistido: dias até expirar (negativo = expirado).
    dias_restantes: int | None = Field(default=None)


class SaudeCertificadoOut(BaseModel):
    """Diagnóstico do certificado ativo."""

    existe: bool
    apelido: str | None = None
    cnpj: str | None = None
    valido_ate: datetime | None = None
    dias_restantes: int | None = None
    expirado: bool | None = None
    aviso: str | None = None
