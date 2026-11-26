"""Contratos de emissão.

`idempotency_key` é obrigatória e por tenant: é o que impede que um webhook de
pagamento reentregue gere duas notas. Todo o resto do contrato é dado de negócio.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.db.models.enums import AmbienteFiscal, OrigemFatura, StatusFatura


class EmissaoIn(BaseModel):
    """Pedido de emissão de NFS-e.

    Campo desconhecido é **recusado**, não ignorado: sem `extra="forbid"` um
    chamador que envia `{"tomador": {...}}` (objeto aninhado, em vez dos campos
    planos) recebe 201 e a nota sai **sem tomador** — perda silenciosa de dado
    fiscal. Descoberto na primeira emissão real em Produção Restrita; ver
    docs/REFERENCIAS.md §14.
    """

    model_config = ConfigDict(extra="forbid")

    idempotency_key: str | None = Field(
        default=None,
        min_length=8,
        max_length=128,
        description=(
            "Chave única por tenant. Pode vir no body (compatibilidade) ou no header "
            "`Idempotency-Key`; o header tem precedência. Reenvio com a mesma chave "
            "devolve a emissão existente."
        ),
        examples=["dz23-venda-8842"],
    )
    valor: Decimal = Field(..., gt=0, max_digits=15, decimal_places=2)
    descricao: str = Field(..., min_length=1, max_length=2000)
    competencia: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}$", description="AAAA-MM; vazio usa a data atual"
    )
    tomador_documento: str | None = Field(default=None, max_length=20)
    tomador_nome: str | None = Field(default=None, max_length=200)
    tomador_email: EmailStr | None = None
    referencia_externa: str | None = Field(
        default=None,
        max_length=255,
        description="Id no sistema de origem (venda no DZ23, atendimento no Brizu).",
    )
    origem: OrigemFatura = OrigemFatura.API
    ambiente: AmbienteFiscal = AmbienteFiscal.HOMOLOGACAO
    municipio_ibge: str | None = Field(
        default=None,
        pattern=r"^\d{7}$",
        description=(
            "Município de incidência (7 dígitos). Obrigatório quando o tenant tem "
            "configuração fiscal para mais de um município no mesmo ambiente: a nota "
            "não escolhe município por conta própria."
        ),
    )

    @field_validator("referencia_externa")
    @classmethod
    def _referencia_nao_vazia(cls, valor: str | None) -> str | None:
        if valor is not None and not valor.strip():
            return None
        return valor


class DocumentoOut(BaseModel):
    """Documento fiscal gerado."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo_documento: str
    ambiente: str
    chave: str | None = None
    emitido_em: datetime | None = None
    tem_xml_autorizado: bool = False


class EmissaoOut(BaseModel):
    """Resultado de uma emissão."""

    invoice_id: uuid.UUID
    status: StatusFatura
    valor: Decimal
    idempotency_key: str
    documento: DocumentoOut | None = None
    chave: str | None = None
    erro: str | None = None
    ja_existia: bool = Field(
        default=False, description="True quando a idempotency_key já tinha sido processada."
    )


class EmissaoDetalheOut(EmissaoOut):
    """Emissão com o XML autorizado, para conferência e download."""

    xml_autorizado: str | None = None
