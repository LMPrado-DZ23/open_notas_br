"""Contratos de simulação tributária.

Valores monetários saem como **string** de propósito: JSON numérico vira `float`
em JavaScript e perde centavo em soma fiscal. Quem consome trata como decimal.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class SimulacaoIn(BaseModel):
    """Entrada explícita do cálculo. Nada é inferido."""

    valor_servico: Decimal = Field(..., gt=0, max_digits=15, decimal_places=2)
    desconto_incondicional: Decimal = Field(default=Decimal("0.00"), ge=0)
    reembolso_repasse: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        description="Reembolso/repasse/ressarcimento já tributado que não integra a base.",
    )
    deducao_reducao: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        description="Dedução/redução de base em locação de imóveis e serviços médicos.",
    )
    iss: Decimal = Field(default=Decimal("0.00"), ge=0)
    pis: Decimal = Field(default=Decimal("0.00"), ge=0)
    cofins: Decimal = Field(default=Decimal("0.00"), ge=0)
    ano_fato_gerador: int = Field(default=2026, ge=2026, le=2100)
    aliquota_cbs: Decimal | None = Field(default=None, ge=0, le=1)
    aliquota_ibs: Decimal | None = Field(default=None, ge=0, le=1)
    mei: bool = Field(default=False, description="MEI: bases de cálculo não aplicáveis (E1302).")
    optante_pendente: bool = Field(default=False, description="Opção pelo Simples pendente.")

    @field_validator("aliquota_ibs")
    @classmethod
    def _par_de_aliquotas(cls, valor: Decimal | None, info) -> Decimal | None:
        cbs = info.data.get("aliquota_cbs")
        if (valor is None) != (cbs is None):
            raise ValueError(
                "informe as duas alíquotas (CBS e IBS) ou nenhuma, para usar a tabela do ano"
            )
        return valor


class SimulacaoOut(BaseModel):
    """Resultado com procedência e ressalvas."""

    base_calculo: str
    ano_fato_gerador: int
    aliquota_cbs: str
    aliquota_ibs: str
    valor_cbs: str
    valor_ibs: str
    valor_total: str
    fonte_aliquota: str
    #: Repartição do IBS, preenchida quando a alíquota vem da tabela oficial.
    aliquota_ibs_uf: str | None = None
    aliquota_ibs_mun: str | None = None
    valor_ibs_uf: str | None = None
    valor_ibs_mun: str | None = None
    valido: bool
    avisos: list[str] = Field(default_factory=list)
    erros: list[str] = Field(default_factory=list)


class AliquotaOut(BaseModel):
    """Alíquota de referência de um ano, com a repartição do IBS."""

    ano: int
    cbs: str
    ibs: str
    ibs_uf: str
    ibs_mun: str
    fonte: str


class ClassificacaoOut(BaseModel):
    """Uma classificação tributária do IBS/CBS em uma vigência."""

    codigo: str
    descricao: str
    tipo_aliquota: str = ""
    nomenclatura: str = ""
    inicio_vigencia: str = ""
    fim_vigencia: str = ""
    anexo: str = ""


class CatalogoOut(BaseModel):
    """Metadados do catálogo, para auditoria da procedência."""

    fonte: str | None = None
    total: int | None = None
    codigos_distintos: int | None = None
    aviso: str | None = None
