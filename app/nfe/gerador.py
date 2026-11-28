"""Monta o XML da NF-e 4.00 na ordem exata do leiaute."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from lxml import etree

from app.core.fiscal import dh_emi
from app.nfe.base import (
    NS_NFE,
    VERSAO,
    NotaFiscal,
    _chave_de_acesso,
    _t,
    digito_verificador,
)

NS = f"{{{NS_NFE}}}"


def _sub(pai: etree._Element, tag: str, valor: object | None) -> etree._Element:
    elemento = etree.SubElement(pai, f"{NS}{tag}")
    if valor is not None:
        elemento.text = str(valor)
    return elemento


def _endereco(pai: etree._Element, tag: str, dados) -> None:
    ender = _sub(pai, tag, None)
    _sub(ender, "xLgr", dados.logradouro)
    _sub(ender, "nro", dados.numero)
    _sub(ender, "xBairro", dados.bairro)
    _sub(ender, "cMun", dados.codigo_municipio)
    _sub(ender, "xMun", dados.municipio)
    _sub(ender, "UF", dados.uf)
    _sub(ender, "CEP", dados.cep)


def gerar_nfe(nota: NotaFiscal) -> bytes:
    """Devolve a NF-e **sem assinatura**, pronta para assinar."""
    nota.validar()

    emissao = nota.dh_emissao or datetime.now(UTC)
    cnf = f"{nota.numero % 100000000:08d}"
    chave43 = _chave_de_acesso(nota, cnf)
    chave = chave43 + digito_verificador(chave43)

    raiz = etree.Element(f"{NS}NFe", nsmap={None: NS_NFE})
    inf = _sub(raiz, "infNFe", None)
    inf.set("versao", VERSAO)
    inf.set("Id", f"NFe{chave}")

    ide = _sub(inf, "ide", None)
    _sub(ide, "cUF", _codigo(nota.emitente.uf))
    _sub(ide, "cNF", cnf)
    _sub(ide, "natOp", nota.natureza_operacao)
    _sub(ide, "mod", "55")
    _sub(ide, "serie", nota.serie)
    _sub(ide, "nNF", nota.numero)
    _sub(ide, "dhEmi", dh_emi(emissao))
    _sub(ide, "tpNF", "1")
    _sub(ide, "idDest", "1" if nota.destinatario.uf == nota.emitente.uf else "2")
    _sub(ide, "cMunFG", nota.emitente.codigo_municipio)
    _sub(ide, "tpImp", "1")
    _sub(ide, "tpEmis", "1")
    _sub(ide, "cDV", chave[-1])
    _sub(ide, "tpAmb", nota.ambiente)
    _sub(ide, "finNFe", "1")
    _sub(ide, "indFinal", "1")
    _sub(ide, "indPres", "1")
    _sub(ide, "procEmi", "0")
    _sub(ide, "verProc", "notasbr-1.0")

    emit = _sub(inf, "emit", None)
    _sub(emit, "CNPJ", nota.emitente.cnpj)
    _sub(emit, "xNome", nota.emitente.nome)
    _endereco(emit, "enderEmit", nota.emitente)
    _sub(emit, "IE", nota.emitente.ie)
    _sub(emit, "CRT", nota.emitente.crt)

    dest = _sub(inf, "dest", None)
    tag_doc = "CNPJ" if len(nota.destinatario.documento) == 14 else "CPF"
    _sub(dest, tag_doc, nota.destinatario.documento)
    _sub(dest, "xNome", nota.destinatario.nome)
    _endereco(dest, "enderDest", nota.destinatario)
    _sub(dest, "indIEDest", "1" if nota.destinatario.ie else "9")
    if nota.destinatario.ie:
        _sub(dest, "IE", nota.destinatario.ie)
    if nota.destinatario.email:
        _sub(dest, "email", nota.destinatario.email)

    total_bruto = Decimal("0")
    total_icms = Decimal("0")
    for numero, item in enumerate(nota.itens, start=1):
        det = _sub(inf, "det", None)
        det.set("nItem", str(numero))
        prod = _sub(det, "prod", None)
        _sub(prod, "cProd", item.codigo)
        _sub(prod, "cEAN", "SEM GTIN")
        _sub(prod, "xProd", item.descricao)
        _sub(prod, "NCM", item.ncm)
        _sub(prod, "CFOP", item.cfop)
        _sub(prod, "uCom", item.unidade)
        _sub(prod, "qCom", _t(item.quantidade, 4))
        _sub(prod, "vUnCom", _t(item.valor_unitario, 10))
        _sub(prod, "vProd", _t(item.valor_total))
        _sub(prod, "cEANTrib", "SEM GTIN")
        _sub(prod, "uTrib", item.unidade)
        _sub(prod, "qTrib", _t(item.quantidade, 4))
        _sub(prod, "vUnTrib", _t(item.valor_unitario, 10))
        _sub(prod, "indTot", "1")
        total_bruto += item.valor_total
        total_icms += item.valor_icms

        imposto = _sub(det, "imposto", None)
        icms = _sub(imposto, "ICMS", None)
        grupo = (
            f"ICMS{item.icms_situacao}"
            if item.icms_situacao == "00"
            else f"ICMSSN{item.icms_situacao}"
        )
        situacao = _sub(icms, grupo, None)
        _sub(situacao, "orig", "0")
        if item.icms_situacao == "00":
            _sub(situacao, "CST", "00")
            _sub(situacao, "modBC", "3")
            _sub(situacao, "vBC", _t(item.valor_total))
            _sub(situacao, "pICMS", _t(item.aliquota_icms))
            _sub(situacao, "vICMS", _t(item.valor_icms))
        else:
            # CSOSN (Simples): sem grupo de base/alíquota, que não existe no leiaute.
            _sub(situacao, "CSOSN", item.icms_situacao)
        pis = _sub(imposto, "PIS", None)
        pis_aliq = _sub(pis, "PISAliq", None)
        _sub(pis_aliq, "CST", "01")
        _sub(pis_aliq, "vBC", _t(item.valor_total))
        _sub(pis_aliq, "pPIS", _t(Decimal("0")))
        _sub(pis_aliq, "vPIS", _t(Decimal("0")))

    total = _sub(inf, "total", None)
    icms_tot = _sub(total, "ICMSTot", None)
    _sub(icms_tot, "vBC", _t(Decimal("0")))
    _sub(icms_tot, "vICMS", _t(total_icms))
    _sub(icms_tot, "vICMSDeson", _t(Decimal("0")))
    _sub(icms_tot, "vFCP", _t(Decimal("0")))
    _sub(icms_tot, "vBCST", _t(Decimal("0")))
    _sub(icms_tot, "vST", _t(Decimal("0")))
    _sub(icms_tot, "vFCPST", _t(Decimal("0")))
    _sub(icms_tot, "vFCPSTRet", _t(Decimal("0")))
    _sub(icms_tot, "vProd", _t(total_bruto))
    _sub(icms_tot, "vFrete", _t(Decimal("0")))
    _sub(icms_tot, "vSeg", _t(Decimal("0")))
    _sub(icms_tot, "vDesc", _t(Decimal("0")))
    _sub(icms_tot, "vII", _t(Decimal("0")))
    _sub(icms_tot, "vIPI", _t(Decimal("0")))
    _sub(icms_tot, "vIPIDevol", _t(Decimal("0")))
    _sub(icms_tot, "vPIS", _t(Decimal("0")))
    _sub(icms_tot, "vCOFINS", _t(Decimal("0")))
    _sub(icms_tot, "vOutro", _t(Decimal("0")))
    _sub(icms_tot, "vNF", _t(total_bruto))

    transp = _sub(inf, "transp", None)
    _sub(transp, "modFrete", nota.modalidade_frete)
    if nota.cnpj_transportadora:
        transportadora = _sub(transp, "transporta", None)
        _sub(transportadora, "CNPJ", nota.cnpj_transportadora)
        if nota.nome_transportadora:
            _sub(transportadora, "xNome", nota.nome_transportadora)

    pag = _sub(inf, "pag", None)
    det_pag = _sub(pag, "detPag", None)
    _sub(det_pag, "tPag", "01")
    _sub(det_pag, "vPag", _t(total_bruto))
    if nota.informacoes_adicionais:
        # UM `infAdic` com `infCpl` dentro. Antes criava dois: um vazio e outro com o
        # texto, e o XSD (maxOccurs=1) recusava toda NF-e com informação adicional.
        inf_adic = _sub(inf, "infAdic", None)
        _sub(inf_adic, "infCpl", nota.informacoes_adicionais)

    return b'<?xml version="1.0" encoding="UTF-8"?>' + etree.tostring(raiz)


def _codigo(uf: str) -> str:
    from app.nfe.base import _codigo_uf

    return _codigo_uf(uf)
