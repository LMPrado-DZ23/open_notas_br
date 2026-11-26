"""Schema de entrada HTTP para geração de CT-e.

Passo 1 de 5 da exposição na API (auditoria §25). Existe separado das dataclasses de domínio
porque a borda HTTP precisa de validação própria: campos obrigatórios, formatos e limites que o
gerador sozinho não impõe.

**Não contém `tenant_id`.** O tenant vem da API key (`app.api.deps.tenant_atual`); aceitá-lo no
corpo permitiria um cliente emitir no CNPJ de outro.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.cte import PapelTomador
from app.cte.gerador import DadosCTe, Parte

#: CNPJ tem 14 dígitos; CPF, 11. Validado aqui para o erro sair como 422, não como exceção.
TAMANHO_CNPJ = 14
TAMANHO_CPF = 11


class ParteIn(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    cnpj: str | None = Field(default=None, min_length=TAMANHO_CNPJ, max_length=TAMANHO_CNPJ)
    cpf: str | None = Field(default=None, min_length=TAMANHO_CPF, max_length=TAMANHO_CPF)
    ie: str | None = Field(default=None, min_length=2, max_length=14)
    municipio_ibge: str = Field(min_length=7, max_length=7, pattern=r"^\d{7}$")
    municipio: str = Field(min_length=1, max_length=60)
    uf: str = Field(min_length=2, max_length=2)
    logradouro: str = Field(default="RUA A", max_length=60)
    numero: str = Field(default="S/N", max_length=60)
    bairro: str = Field(default="CENTRO", max_length=60)

    @field_validator("cnpj", "cpf")
    @classmethod
    def _so_digitos(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        if not valor.isdigit():
            raise ValueError("documento deve conter apenas dígitos")
        return valor

    def para_dominio(self) -> Parte:
        return Parte(
            nome=self.nome,
            cnpj=self.cnpj,
            cpf=self.cpf,
            ie=self.ie,
            municipio_ibge=self.municipio_ibge,
            municipio=self.municipio,
            uf=self.uf,
            logradouro=self.logradouro,
            numero=self.numero,
            bairro=self.bairro,
        )


class CTeIn(BaseModel):
    numero: int = Field(ge=1, le=999_999_999)
    serie: int = Field(ge=0, le=999)
    chave: str = Field(min_length=44, max_length=44, pattern=r"^\d{44}$")
    emitente: ParteIn
    destinatario: ParteIn
    papel_tomador: PapelTomador
    valor_total: Decimal = Field(gt=0)
    peso: Decimal = Field(gt=0)
    produto: str = Field(min_length=1, max_length=120)
    data_emissao: datetime
    rntrc: str = Field(min_length=8, max_length=8, pattern=r"^\d{8}$")
    chaves_documentos: tuple[str, ...] = Field(min_length=1)

    @field_validator("chaves_documentos")
    @classmethod
    def _chaves_validas(cls, valor: tuple[str, ...]) -> tuple[str, ...]:
        for chave in valor:
            if len(chave) != 44 or not chave.isdigit():
                raise ValueError("cada chave de documento deve ter 44 dígitos")
        return valor

    def para_dominio(self) -> DadosCTe:
        return DadosCTe(
            numero=self.numero,
            serie=self.serie,
            chave=self.chave,
            emitente=self.emitente.para_dominio(),
            destinatario=self.destinatario.para_dominio(),
            papel_tomador=self.papel_tomador,
            valor_total=self.valor_total,
            peso=self.peso,
            produto=self.produto,
            data_emissao=self.data_emissao,
            rntrc=self.rntrc,
            chaves_documentos=self.chaves_documentos,
        )
