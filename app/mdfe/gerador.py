"""Gerador de XML de MDF-e 3.00, validado contra o schema oficial.

Mesmo desenho do CT-e: `gerar()` monta na ordem extraída do `xs:sequence`; `gerar_assinado()`
assina e valida. O MDF-e só é válido assinado.

Escopo: modal rodoviário (`rodo`), emissão normal, carga própria. Contingência e outros modais
ficam para quando houver caso real.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from lxml import etree

from app.core.fiscal import dh_emi
from app.mdfe import validar

NS = "http://www.portalfiscal.inf.br/mdfe"
VERSAO = "3.00"


def _sub(pai, tag, texto=None):
    el = etree.SubElement(pai, tag)
    if texto is not None:
        el.text = str(texto)
    return el


@dataclass(frozen=True, slots=True)
class Emitente:
    cnpj: str
    nome: str
    ie: str
    municipio_ibge: str
    municipio: str
    uf: str
    logradouro: str = "RUA A"
    numero: str = "S/N"
    bairro: str = "CENTRO"


@dataclass(frozen=True, slots=True)
class MunicipioCarregamento:
    codigo_ibge: str
    nome: str


@dataclass(frozen=True, slots=True)
class Descarga:
    """`infMunDescarga`: onde a carga será descarregada, e quais NF-e vão para lá."""

    codigo_ibge: str
    nome: str
    chaves_nfe: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DadosMDFe:
    numero: int
    serie: int
    chave: str
    emitente: Emitente
    uf_inicio: str
    uf_fim: str
    municipios_carregamento: tuple[MunicipioCarregamento, ...]
    valor_carga: Decimal
    peso: Decimal
    data_emissao: datetime
    descargas: tuple[Descarga, ...]


def gerar(dados: DadosMDFe) -> etree._Element:
    if len(dados.chave) != 44 or not dados.chave.isdigit():
        raise ValueError("chave precisa ter 44 dígitos")
    if not dados.descargas:
        raise ValueError("MDF-e exige ao menos um município de descarga (infMunDescarga)")
    if not any(d.chaves_nfe for d in dados.descargas):
        raise ValueError("MDF-e exige ao menos uma chave de NF-e em infDoc")
    if not dados.municipios_carregamento:
        raise ValueError("MDF-e exige ao menos um município de carregamento")

    raiz = etree.Element("MDFe", nsmap={None: NS})
    inf = _sub(raiz, "infMDFe")
    inf.set("Id", f"MDFe{dados.chave}")
    inf.set("versao", VERSAO)

    ide = _sub(inf, "ide")
    _sub(ide, "cUF", dados.emitente.municipio_ibge[:2])
    _sub(ide, "tpAmb", "2")
    _sub(ide, "tpEmit", "1")
    _sub(ide, "mod", "58")
    _sub(ide, "serie", dados.serie)
    _sub(ide, "nMDF", dados.numero)
    _sub(ide, "cMDF", dados.chave[35:43])
    _sub(ide, "cDV", dados.chave[-1])
    _sub(ide, "modal", "1")  # 1 = rodoviário
    _sub(ide, "dhEmi", dh_emi(dados.data_emissao))
    _sub(ide, "tpEmis", "1")
    _sub(ide, "procEmi", "0")
    _sub(ide, "verProc", "open-notas-br")
    _sub(ide, "UFIni", dados.uf_inicio)
    _sub(ide, "UFFim", dados.uf_fim)
    for municipio in dados.municipios_carregamento:
        carrega = _sub(ide, "infMunCarrega")
        _sub(carrega, "cMunCarrega", municipio.codigo_ibge)
        _sub(carrega, "xMunCarrega", municipio.nome)

    emi = _sub(inf, "emit")
    _sub(emi, "CNPJ", dados.emitente.cnpj)
    _sub(emi, "IE", dados.emitente.ie)
    _sub(emi, "xNome", dados.emitente.nome)
    ender = _sub(emi, "enderEmit")
    _sub(ender, "xLgr", dados.emitente.logradouro)
    _sub(ender, "nro", dados.emitente.numero)
    _sub(ender, "xBairro", dados.emitente.bairro)
    _sub(ender, "cMun", dados.emitente.municipio_ibge)
    _sub(ender, "xMun", dados.emitente.municipio)
    _sub(ender, "UF", dados.emitente.uf)

    inf_modal = _sub(inf, "infModal")
    inf_modal.set("versaoModal", VERSAO)
    _sub(inf_modal, "rodo")

    inf_doc = _sub(inf, "infDoc")
    for descarga in dados.descargas:
        mun = _sub(inf_doc, "infMunDescarga")
        _sub(mun, "cMunDescarga", descarga.codigo_ibge)
        _sub(mun, "xMunDescarga", descarga.nome)
        for chave_nfe in descarga.chaves_nfe:
            if len(chave_nfe) != 44 or not chave_nfe.isdigit():
                raise ValueError(f"chave de NF-e inválida: {chave_nfe!r}")
            _sub(_sub(mun, "infNFe"), "chNFe", chave_nfe)

    tot = _sub(inf, "tot")
    _sub(tot, "vCarga", f"{dados.valor_carga:.2f}")
    _sub(tot, "cUnid", "01")
    _sub(tot, "qCarga", f"{dados.peso:.4f}")

    return raiz


def gerar_assinado(dados: DadosMDFe, certificado) -> bytes:
    """Gera, assina e **valida**. Caminho a usar em produção."""
    from app.nfe.assinatura import assinar_nfe

    xml = b'<?xml version="1.0" encoding="UTF-8"?>' + etree.tostring(gerar(dados))
    assinado = assinar_nfe(xml, certificado)
    validar(assinado)
    return assinado
