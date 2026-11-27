"""Contratos de entrada e saída de tenant.

`TenantCriadoOut` é o **único** lugar onde a API key aparece em claro. Depois
disso, só o prefixo é recuperável — o segredo não é armazenado.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.db.models.enums import (
    AmbienteFiscal,
    ProvedorFiscal,
    StatusTenant,
)

#: Slug: minúsculas, dígitos e hífen; não começa nem termina com hífen.
_PADRAO_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


class TenantCreate(BaseModel):
    """Dados para abrir uma conta."""

    slug: str = Field(..., min_length=2, max_length=64, examples=["barbearia-centro"])
    nome: str = Field(..., min_length=2, max_length=200, examples=["Barbearia Centro LTDA"])
    email_contato: EmailStr | None = None
    webhook_url: str | None = Field(default=None, max_length=500)

    @field_validator("slug")
    @classmethod
    def _validar_slug(cls, valor: str) -> str:
        normalizado = valor.strip().lower()
        if not _PADRAO_SLUG.match(normalizado):
            raise ValueError(
                "slug deve conter apenas minúsculas, dígitos e hífen, "
                "sem começar ou terminar com hífen"
            )
        return normalizado

    @field_validator("webhook_url")
    @classmethod
    def _validar_webhook(cls, valor: str | None) -> str | None:
        if valor and not valor.startswith(("http://", "https://")):
            raise ValueError("webhook_url deve começar com http:// ou https://")
        return valor


class TenantOut(BaseModel):
    """Visão pública do tenant. Nunca inclui hash nem segredo."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    nome: str
    status: StatusTenant
    email_contato: str | None = None
    api_key_prefix: str
    webhook_url: str | None = None
    created_at: datetime


class TenantCriadoOut(TenantOut):
    """Resposta da criação: inclui a API key em claro, uma única vez."""

    api_key: str = Field(
        ...,
        description=(
            "API key em claro. Guarde agora: o servidor armazena apenas o hash e "
            "não consegue exibir este valor novamente."
        ),
    )
    webhook_secret: str | None = Field(
        default=None,
        description="Segredo HMAC para o webhook do tenant. Também exibido uma única vez.",
    )


class RotacionarChaveIn(BaseModel):
    """Parâmetros opcionais da rotação. Sem corpo, o comportamento antigo é preservado.

    `escopos`: `leitura` (GET/HEAD/OPTIONS) e `emissao` (escritas). Omitir = sem restrição — é o que
    mantém compatibilidade com quem já usa a chave para tudo.
    """

    dias_validade: int | None = Field(default=None, ge=1, le=3650)
    escopos: list[Literal["leitura", "emissao"]] | None = None


class TenantKeyRotacionadaOut(BaseModel):
    """Nova API key após rotação. A anterior deixa de funcionar imediatamente."""

    tenant_id: uuid.UUID
    api_key: str
    api_key_prefix: str
    api_key_expira_em: datetime | None = None
    api_key_escopos: list[str] | None = None


class TenantFiscalConfigIn(BaseModel):
    """Configuração fiscal de um município para o tenant."""

    municipio_ibge: str = Field(..., min_length=7, max_length=7, pattern=r"^\d{7}$")
    municipio_nome: str | None = Field(default=None, max_length=120)
    uf: str | None = Field(default=None, min_length=2, max_length=2)
    aderente_emissor_nacional: bool = False
    provedor: ProvedorFiscal = ProvedorFiscal.NACIONAL
    ambiente: AmbienteFiscal = AmbienteFiscal.HOMOLOGACAO
    regime_tributario: int = Field(default=1, ge=1, le=4)
    simples_nacional: bool = True
    optante_mei: bool = False
    aliquota_iss: Decimal | None = Field(default=None, ge=0, le=1)
    serie_dps: str = Field(default="1", max_length=5)
    proximo_numero_dps: int = Field(default=1, ge=1)
    inscricao_municipal: str | None = Field(default=None, max_length=30)
    cnae_principal: str | None = Field(default=None, max_length=9)
    codigo_tributacao_nacional: str | None = Field(default=None, max_length=10)

    @field_validator("uf")
    @classmethod
    def _uf_maiuscula(cls, valor: str | None) -> str | None:
        return valor.upper() if valor else valor


class TenantFiscalConfigOut(TenantFiscalConfigIn):
    """Configuração fiscal persistida."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PaginaTenants(BaseModel):
    """Página de tenants."""

    total: int
    limite: int
    deslocamento: int
    itens: list[TenantOut]
