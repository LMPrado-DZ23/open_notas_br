"""Schema de entrada HTTP para geração de MDF-e.

Passo 1 de 5 da exposição na API (auditoria §25). Sem `tenant_id` no corpo: o tenant vem da
API key.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.mdfe.gerador import DadosMDFe, Descarga, Emitente, MunicipioCarregamento


class EmitenteIn(BaseModel):
    cnpj: str = Field(min_length=14, max_length=14)
    nome: str = Field(min_length=1, max_length=60)
    ie: str = Field(min_length=2, max_length=14)
    municipio_ibge: str = Field(min_length=7, max_length=7, pattern=r"^\d{7}$")
    municipio: str = Field(min_length=1, max_length=60)
    uf: str = Field(min_length=2, max_length=2)
    logradouro: str = Field(default="RUA A", max_length=60)
    numero: str = Field(default="S/N", max_length=60)
    bairro: str = Field(default="CENTRO", max_length=60)

    def para_dominio(self) -> Emitente:
        return Emitente(
            cnpj=self.cnpj,
            nome=self.nome,
            ie=self.ie,
            municipio_ibge=self.municipio_ibge,
            municipio=self.municipio,
            uf=self.uf,
            logradouro=self.logradouro,
            numero=self.numero,
            bairro=self.bairro,
        )


class MunicipioCarregamentoIn(BaseModel):
    codigo_ibge: str = Field(min_length=7, max_length=7, pattern=r"^\d{7}$")
    nome: str = Field(min_length=1, max_length=60)

    def para_dominio(self) -> MunicipioCarregamento:
        return MunicipioCarregamento(codigo_ibge=self.codigo_ibge, nome=self.nome)


class DescargaIn(BaseModel):
    codigo_ibge: str = Field(min_length=7, max_length=7, pattern=r"^\d{7}$")
    nome: str = Field(min_length=1, max_length=60)
    chaves_nfe: tuple[str, ...] = Field(min_length=1)

    @field_validator("chaves_nfe")
    @classmethod
    def _chaves_validas(cls, valor: tuple[str, ...]) -> tuple[str, ...]:
        for chave in valor:
            if len(chave) != 44 or not chave.isdigit():
                raise ValueError("cada chave de NF-e deve ter 44 dígitos")
        return valor

    def para_dominio(self) -> Descarga:
        return Descarga(codigo_ibge=self.codigo_ibge, nome=self.nome, chaves_nfe=self.chaves_nfe)


class MDFeIn(BaseModel):
    numero: int = Field(ge=1, le=999_999_999)
    serie: int = Field(ge=0, le=999)
    chave: str = Field(min_length=44, max_length=44, pattern=r"^\d{44}$")
    emitente: EmitenteIn
    uf_inicio: str = Field(min_length=2, max_length=2)
    uf_fim: str = Field(min_length=2, max_length=2)
    municipios_carregamento: tuple[MunicipioCarregamentoIn, ...] = Field(min_length=1)
    valor_carga: Decimal = Field(gt=0)
    peso: Decimal = Field(gt=0)
    data_emissao: datetime
    descargas: tuple[DescargaIn, ...] = Field(min_length=1)

    def para_dominio(self) -> DadosMDFe:
        return DadosMDFe(
            numero=self.numero,
            serie=self.serie,
            chave=self.chave,
            emitente=self.emitente.para_dominio(),
            uf_inicio=self.uf_inicio,
            uf_fim=self.uf_fim,
            municipios_carregamento=tuple(m.para_dominio() for m in self.municipios_carregamento),
            valor_carga=self.valor_carga,
            peso=self.peso,
            data_emissao=self.data_emissao,
            descargas=tuple(d.para_dominio() for d in self.descargas),
        )
