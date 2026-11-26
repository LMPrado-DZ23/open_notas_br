"""Gerador de XML de CT-e 4.00, validado contra o schema oficial.

Ordem de `ide` extraída do XSD (`docs/cte-ide-ordem.md`). Grupo de tomador decidido por
`PapelTomador`. Modal rodoviário com `RNTRC` informado pelo emitente — o leiaute exige.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from lxml import etree

from app.cte import PapelTomador, validar

NS = "http://www.portalfiscal.inf.br/cte"
VERSAO = "4.00"


def _n(valor: Decimal) -> str:
    return f"{valor:.2f}"


def _sub(pai, tag, texto=None):
    el = etree.SubElement(pai, tag)
    if texto is not None:
        el.text = str(texto)
    return el


@dataclass(frozen=True, slots=True)
class Parte:
    nome: str
    cnpj: str | None = None
    cpf: str | None = None
    ie: str | None = None
    municipio_ibge: str = "5208707"
    municipio: str = "GOIANIA"
    uf: str = "GO"
    logradouro: str = "RUA A"
    numero: str = "S/N"
    bairro: str = "CENTRO"

    def documento(self, pai, tag_cnpj="CNPJ", tag_cpf="CPF") -> None:
        if self.cnpj:
            _sub(pai, tag_cnpj, self.cnpj)
        elif self.cpf:
            _sub(pai, tag_cpf, self.cpf)
        else:
            raise ValueError("parte sem CNPJ nem CPF")


@dataclass(frozen=True, slots=True)
class DadosCTe:
    numero: int
    serie: int
    chave: str
    emitente: Parte
    destinatario: Parte
    papel_tomador: PapelTomador
    valor_total: Decimal
    peso: Decimal
    produto: str
    data_emissao: datetime
    rntrc: str
    chaves_documentos: tuple[str, ...]


def _endereco(pai, parte: Parte, tag: str, *, com_cep: bool) -> None:
    el = _sub(pai, tag)
    _sub(el, "xLgr", parte.logradouro)
    _sub(el, "nro", parte.numero)
    _sub(el, "xBairro", parte.bairro)
    _sub(el, "cMun", parte.municipio_ibge)
    _sub(el, "xMun", parte.municipio)
    _sub(el, "UF", parte.uf)
    if com_cep:
        _sub(el, "CEP", "74000000")


def gerar(dados: DadosCTe) -> bytes:
    if len(dados.chave) != 44 or not dados.chave.isdigit():
        raise ValueError("chave precisa ter 44 dígitos")
    if not dados.chaves_documentos:
        raise ValueError("CT-e exige ao menos uma chave de documento de carga")
    if not dados.rntrc:
        raise ValueError("CT-e rodoviário exige RNTRC do emitente")

    cte = etree.Element("CTe", nsmap={None: NS})
    inf = _sub(cte, "infCte")
    inf.set("Id", f"CTe{dados.chave}")
    inf.set("versao", VERSAO)

    ide = _sub(inf, "ide")
    _sub(ide, "cUF", dados.emitente.municipio_ibge[:2])
    _sub(ide, "cCT", dados.chave[35:43])
    _sub(ide, "CFOP", "5353")
    _sub(ide, "natOp", "PRESTACAO DE SERVICO DE TRANSPORTE")
    _sub(ide, "mod", "57")
    _sub(ide, "serie", dados.serie)
    _sub(ide, "nCT", dados.numero)
    _sub(ide, "dhEmi", dados.data_emissao.strftime("%Y-%m-%dT%H:%M:%S-03:00"))
    _sub(ide, "tpImp", "1")
    _sub(ide, "tpEmis", "1")
    _sub(ide, "cDV", dados.chave[-1])
    _sub(ide, "tpAmb", "2")
    _sub(ide, "tpCTe", "0")
    _sub(ide, "procEmi", "0")
    _sub(ide, "verProc", "open-notas-br")
    _sub(ide, "cMunEnv", dados.emitente.municipio_ibge)
    _sub(ide, "xMunEnv", dados.emitente.municipio)
    _sub(ide, "UFEnv", dados.emitente.uf)
    _sub(ide, "modal", "01")
    _sub(ide, "tpServ", "0")
    _sub(ide, "cMunIni", dados.emitente.municipio_ibge)
    _sub(ide, "xMunIni", dados.emitente.municipio)
    _sub(ide, "UFIni", dados.emitente.uf)
    _sub(ide, "cMunFim", dados.destinatario.municipio_ibge)
    _sub(ide, "xMunFim", dados.destinatario.municipio)
    _sub(ide, "UFFim", dados.destinatario.uf)
    _sub(ide, "retira", "1")
    _sub(ide, "indIEToma", "1")

    grupo = _sub(ide, dados.papel_tomador.grupo)
    _sub(grupo, "toma", dados.papel_tomador.value)
    if dados.papel_tomador.exige_dados_proprios:
        dados.destinatario.documento(grupo)
        if dados.destinatario.ie:
            _sub(grupo, "IE", dados.destinatario.ie)
        _sub(grupo, "xNome", dados.destinatario.nome)
        # `toma4` exige o endereço do tomador: ele não é parte do documento.
        _endereco(grupo, dados.destinatario, "enderToma", com_cep=False)

    emi = _sub(inf, "emit")
    dados.emitente.documento(emi)
    if dados.emitente.ie:
        _sub(emi, "IE", dados.emitente.ie)
    _sub(emi, "xNome", dados.emitente.nome)
    _endereco(emi, dados.emitente, "enderEmit", com_cep=False)
    _sub(emi, "CRT", "3")

    dest = _sub(inf, "dest")
    dados.destinatario.documento(dest)
    _sub(dest, "xNome", dados.destinatario.nome)
    _endereco(dest, dados.destinatario, "enderDest", com_cep=False)

    vprest = _sub(inf, "vPrest")
    _sub(vprest, "vTPrest", _n(dados.valor_total))
    _sub(vprest, "vRec", _n(dados.valor_total))
    comp = _sub(vprest, "Comp")
    _sub(comp, "xNome", "FRETE")
    _sub(comp, "vComp", _n(dados.valor_total))

    imp = _sub(inf, "imp")
    icms = _sub(imp, "ICMS")
    icms00 = _sub(icms, "ICMS00")
    _sub(icms00, "CST", "00")
    _sub(icms00, "vBC", _n(dados.valor_total))
    _sub(icms00, "pICMS", "12.00")
    _sub(icms00, "vICMS", _n(dados.valor_total * Decimal("0.12")))

    norm = _sub(inf, "infCTeNorm")
    carga = _sub(norm, "infCarga")
    _sub(carga, "vCarga", _n(dados.valor_total))
    _sub(carga, "proPred", dados.produto)
    inf_q = _sub(carga, "infQ")
    _sub(inf_q, "cUnid", "01")
    _sub(inf_q, "tpMed", "PESO BRUTO")
    _sub(inf_q, "qCarga", f"{dados.peso:.4f}")

    inf_doc = _sub(norm, "infDoc")
    for chave_doc in dados.chaves_documentos:
        if len(chave_doc) != 44 or not chave_doc.isdigit():
            raise ValueError(f"chave de documento inválida: {chave_doc!r}")
        _sub(_sub(inf_doc, "infNFe"), "chave", chave_doc)

    inf_modal = _sub(norm, "infModal")
    inf_modal.set("versaoModal", VERSAO)
    rodo = _sub(inf_modal, "rodo")
    _sub(rodo, "RNTRC", dados.rntrc)

    # O CT-e só é válido **assinado**: o schema exige `Signature` depois de `infCte`.
    # Por isso `gerar()` devolve a árvore e quem chama assina; `gerar_assinado()` faz os dois
    # e valida o resultado.
    return cte


def gerar_assinado(dados: DadosCTe, certificado) -> bytes:
    """Gera, assina e **valida**. É o caminho que deve ser usado em produção."""
    from app.nfe.assinatura import assinar_nfe

    raiz = gerar(dados)
    xml = b'<?xml version="1.0" encoding="UTF-8"?>' + etree.tostring(raiz)
    assinado = assinar_nfe(xml, certificado)
    validar(assinado)
    return assinado
