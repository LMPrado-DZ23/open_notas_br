"""Geração de NF-e 4.00 e assinatura, validada contra o XSD oficial.

Escopo desta fatia (F9.2): montar o XML da NF-e a partir de dados de negócio,
assinar no mesmo padrão do resto do projeto e provar que o resultado valida contra
o `nfe_v4.00.xsd` oficial. **Não** inclui transporte SOAP nem autorização — isso é
F9.3 em diante, e depende de credenciamento na SEFAZ da UF.

Layout: leiaute 4.00, o vigente. A ordem dos grupos segue o XSD; trocar a ordem é a
causa mais comum de recusa por schema, e o teste de validação existe para pegar isso.

O que o gerador **não** decide: regime tributário, CST/CSOSN, alíquotas, NCM e CFOP.
São dado fiscal de entrada — o sistema não inventa. Sem eles, a nota é recusada pela
SEFAZ por regra de negócio, e é assim que deve ser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
VERSAO = "4.00"


class ErroDeNFe(Exception):
    """Dados insuficientes ou inconsistentes para montar a NF-e."""


def _t(valor: Decimal, casas: int = 2) -> str:
    """Formata decimal com o número de casas que o leiaute exige."""
    return f"{Decimal(valor).quantize(Decimal(1).scaleb(-casas)):.{casas}f}"


@dataclass(slots=True)
class Emitente:
    cnpj: str
    nome: str
    ie: str
    crt: str  # 1=Simples, 2=Simples excesso, 3=Normal
    logradouro: str
    numero: str
    bairro: str
    municipio: str
    codigo_municipio: str
    uf: str
    cep: str
    telefone: str | None = None


@dataclass(slots=True)
class Destinatario:
    documento: str  # CPF (11) ou CNPJ (14)
    nome: str
    logradouro: str
    numero: str
    bairro: str
    municipio: str
    codigo_municipio: str
    uf: str
    cep: str
    ie: str | None = None
    email: str | None = None


@dataclass(slots=True)
class Item:
    codigo: str
    descricao: str
    ncm: str
    cfop: str
    unidade: str
    quantidade: Decimal
    valor_unitario: Decimal
    valor_total: Decimal
    cst: str
    icms_situacao: str = "00"  # CST ou CSOSN
    #: Alíquota do ICMS em percentual (ex.: 18.00). Zero para isento/ST.
    aliquota_icms: Decimal = Decimal("0")
    valor_icms: Decimal = Decimal("0")


@dataclass(slots=True)
class NotaFiscal:
    """Dados de uma NF-e pronta para virar XML."""

    numero: int
    serie: int
    emitente: Emitente
    destinatario: Destinatario
    itens: list[Item]
    natureza_operacao: str = "VENDA DE MERCADORIA"
    #: 1=produção, 2=homologação.
    ambiente: str = "2"
    #: Presencial=1, internet=2, teleatendimento=3, outros=9.
    modalidade_frete: str = "9"
    cnpj_transportadora: str | None = None
    nome_transportadora: str | None = None
    informacoes_adicionais: str | None = field(default=None)
    dh_emissao: datetime | None = None

    def validar(self) -> None:
        if not self.itens:
            raise ErroDeNFe("a nota precisa de ao menos um item")
        if not re.fullmatch(r"\d{14}", self.emitente.cnpj):
            raise ErroDeNFe("CNPJ do emitente deve ter 14 dígitos")
        if not re.fullmatch(r"\d{11}|\d{14}", self.destinatario.documento):
            raise ErroDeNFe("destinatário deve ser CPF (11) ou CNPJ (14)")
        if self.ambiente not in ("1", "2"):
            raise ErroDeNFe("ambiente deve ser '1' (produção) ou '2' (homologação)")
        if not self.emitente.crt:
            raise ErroDeNFe("CRT do emitente é obrigatório")
        for indice, item in enumerate(self.itens, start=1):
            if not re.fullmatch(r"\d{8}", item.ncm):
                raise ErroDeNFe(f"item {indice}: NCM deve ter 8 dígitos")
            if not re.fullmatch(r"\d{4}", item.cfop):
                raise ErroDeNFe(f"item {indice}: CFOP deve ter 4 dígitos")


def _chave_de_acesso(nota: NotaFiscal, cnf: str) -> str:
    """Monta a chave de 44 posições.

    `cDV` entra depois, como dígito verificador; aqui é só a base.
    """
    uf = _codigo_uf(nota.emitente.uf)
    emissao = nota.dh_emissao or datetime.now()
    return f"{uf}{emissao:%y%m}{nota.emitente.cnpj}55{nota.serie:03d}{nota.numero:09d}1{cnf}"


UF_CODIGO = {
    "RO": "11",
    "AC": "12",
    "AM": "13",
    "RR": "14",
    "PA": "15",
    "AP": "16",
    "TO": "17",
    "MA": "21",
    "PI": "22",
    "CE": "23",
    "RN": "24",
    "PB": "25",
    "PE": "26",
    "AL": "27",
    "SE": "28",
    "BA": "29",
    "MG": "31",
    "ES": "32",
    "RJ": "33",
    "SP": "35",
    "PR": "41",
    "SC": "42",
    "RS": "43",
    "MS": "50",
    "MT": "51",
    "GO": "52",
    "DF": "53",
}


def _codigo_uf(uf: str) -> str:
    codigo = UF_CODIGO.get((uf or "").upper())
    if codigo is None:
        raise ErroDeNFe(f"UF desconhecida: {uf!r}")
    return codigo


def digito_verificador(chave43: str) -> str:
    """Módulo 11 da chave de acesso, pesos 2..9 da direita para a esquerda."""
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = 0
    for posicao, caractere in enumerate(reversed(chave43)):
        soma += int(caractere) * pesos[posicao % 8]
    resto = soma % 11
    dv = 11 - resto
    return "0" if dv >= 10 else str(dv)
