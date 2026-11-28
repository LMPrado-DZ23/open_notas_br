"""Construtores de XML sintético para os testes.

Nenhum documento aqui é real: CNPJ, números e valores são inventados e servem só
para exercitar as regras. O CNPJ 11.222.333/0001-81 é o exemplo didático público
usado em documentação contábil brasileira; o CPF 111.444.777-35, idem.
"""

from __future__ import annotations

import base64
from xml.etree import ElementTree as ET

from notasbr.chave import montar_chave
from notasbr.xml_util import navegar

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_CTE = "http://www.portalfiscal.inf.br/cte"
NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"

CNPJ_EMITENTE = "11222333000181"
CNPJ_DESTINATARIO = "11222333000181"

_VALOR_DIGEST = base64.b64encode(b"\x00" * 20).decode()
#: `SignatureValue` de um RSA-2048 tem 256 bytes. O stub usava o mesmo valor de 20 bytes do
#: digest, o que não é assinatura possível — e o auditor passou a dizer isso.
_VALOR_ASSINATURA = base64.b64encode(b"\x00" * 256).decode()


# ----------------------------------------------------------------------
# utilidades de árvore
# ----------------------------------------------------------------------
def _sub(pai: ET.Element, tag: str, texto: str | None = None, **attrs: str) -> ET.Element:
    elemento = ET.SubElement(pai, tag, attrs)
    if texto is not None:
        elemento.text = texto
    return elemento


def para_bytes(raiz: ET.Element) -> bytes:
    """Serializa preservando o namespace default declarado na raiz."""
    return ET.tostring(raiz, encoding="utf-8", xml_declaration=True)


def de_bytes(dados: bytes) -> ET.Element:
    return ET.fromstring(dados)


def achar(raiz: ET.Element, caminho: str) -> ET.Element | None:
    if not caminho.strip("/"):
        return raiz
    return navegar(raiz, caminho)


def transformar(dados: bytes, funcao) -> bytes:
    """Aplica `funcao(raiz)` sobre a árvore e devolve os bytes resultantes.

    Escape para mutações que os helpers de caminho não cobrem (atributos de
    irmãos repetidos, remoção de grupo inteiro).
    """
    raiz = de_bytes(dados)
    funcao(raiz)
    return para_bytes(raiz)


def com_atributo(dados: bytes, caminho: str, atributo: str, valor: str) -> bytes:
    """Troca o atributo de um elemento identificado por caminho de nomes locais."""
    raiz = de_bytes(dados)
    elemento = achar(raiz, caminho)
    assert elemento is not None, f"caminho inexistente no fixture: {caminho}"
    elemento.set(atributo, valor)
    return para_bytes(raiz)


def com_campo(dados: bytes, caminho: str, valor: str) -> bytes:
    """Devolve o XML com o texto de `caminho` trocado por `valor`."""
    raiz = de_bytes(dados)
    elemento = achar(raiz, caminho)
    assert elemento is not None, f"caminho inexistente no fixture: {caminho}"
    elemento.text = valor
    return para_bytes(raiz)


def sem_campo(dados: bytes, caminho: str) -> bytes:
    """Devolve o XML sem o elemento `caminho`."""
    raiz = de_bytes(dados)
    alvo = achar(raiz, caminho)
    assert alvo is not None, f"caminho inexistente no fixture: {caminho}"
    for pai in raiz.iter():
        if alvo in list(pai):
            pai.remove(alvo)
            return para_bytes(raiz)
    raise AssertionError(f"não foi possível remover {caminho}")


def _assinatura(pai: ET.Element, referencia: str) -> None:
    """Signature estruturalmente plausível, sem certificado (para teste offline)."""
    assinatura = _sub(pai, "Signature", xmlns=NS_DSIG)
    info = _sub(assinatura, "SignedInfo")
    _sub(
        info, "CanonicalizationMethod", algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
    )
    _sub(info, "SignatureMethod", algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1")
    referencia_elem = _sub(info, "Reference", URI=f"#{referencia}")
    _sub(referencia_elem, "DigestMethod", algorithm="http://www.w3.org/2000/09/xmldsig#sha1")
    _sub(referencia_elem, "DigestValue", _VALOR_DIGEST)
    _sub(assinatura, "SignatureValue", _VALOR_ASSINATURA)


def _endereco(
    pai: ET.Element, uf: str, municipio: str = "3550308", nome: str = "Sao Paulo"
) -> None:
    _sub(pai, "xLgr", "Rua Exemplo")
    _sub(pai, "nro", "100")
    _sub(pai, "xBairro", "Centro")
    _sub(pai, "cMun", municipio)
    _sub(pai, "xMun", nome)
    _sub(pai, "UF", uf)
    _sub(pai, "CEP", "01001000")
    _sub(pai, "cPais", "1058")
    _sub(pai, "xPais", "Brasil")


# ----------------------------------------------------------------------
# NF-e
# ----------------------------------------------------------------------
def nfe(
    *,
    c_uf: str = "35",
    aamm: str = "2501",
    dh_emi: str = "2025-01-15T10:30:00-03:00",
    serie: str = "1",
    numero: str = "123",
    c_nf: str = "12345678",
    modelo: str = "55",
    valor_item: str = "1000.00",
    quantidade: str = "10.0000",
    com_assinatura: bool = True,
    com_protocolo: bool = True,
    com_pagamento: bool = True,
    dois_itens: bool = False,
    tp_amb: str = "1",
    cnpj_emitente: str = CNPJ_EMITENTE,
    cfop: str = "5102",
    ncm: str = "94036000",
    cst: str = "00",
    crt: str = "3",
    volumes: list[dict[str, str]] | None = None,
) -> bytes:
    """Constrói uma NF-e 4.00 sintética, por padrão autoconsistente."""
    total = f"{float(valor_item) * (2 if dois_itens else 1):.2f}"
    chave = montar_chave(
        c_uf=c_uf,
        aamm=aamm,
        cnpj=cnpj_emitente,
        modelo=modelo,
        serie=serie,
        numero=numero,
        tp_emis="1",
        c_nf=c_nf,
    )

    raiz = ET.Element("nfeProc", {"versao": "4.00", "xmlns": NS_NFE})
    nfe_elem = _sub(raiz, "NFe")
    inf = _sub(nfe_elem, "infNFe", versao="4.00", Id=f"NFe{chave}")

    ide = _sub(inf, "ide")
    _sub(ide, "cUF", c_uf)
    _sub(ide, "cNF", c_nf)
    _sub(ide, "natOp", "Venda de mercadoria")
    _sub(ide, "mod", modelo)
    _sub(ide, "serie", serie)
    _sub(ide, "nNF", numero)
    _sub(ide, "dhEmi", dh_emi)
    _sub(ide, "tpNF", "1")
    _sub(ide, "idDest", "1")
    _sub(ide, "cMunFG", "3550308")
    _sub(ide, "tpImp", "1")
    _sub(ide, "tpEmis", "1")
    _sub(ide, "cDV", chave[-1])
    _sub(ide, "tpAmb", tp_amb)
    _sub(ide, "finNFe", "1")
    _sub(ide, "indFinal", "1")
    _sub(ide, "indPres", "1")
    _sub(ide, "procEmi", "0")
    _sub(ide, "verProc", "notasbr-teste")

    emit = _sub(inf, "emit")
    _sub(emit, "CNPJ", cnpj_emitente)
    _sub(emit, "xNome", "Empresa Exemplo LTDA")
    _endereco(_sub(emit, "enderEmit"), "SP")
    _sub(emit, "IE", "111111111111")
    _sub(emit, "CRT", crt)

    dest = _sub(inf, "dest")
    _sub(dest, "CNPJ", CNPJ_DESTINATARIO)
    _sub(dest, "xNome", "Cliente Exemplo SA")
    _endereco(_sub(dest, "enderDest"), "SP")
    _sub(dest, "indIEDest", "1")
    _sub(dest, "IE", "222222222222")

    def item(indice: int) -> None:
        det = _sub(inf, "det", nItem=str(indice))
        prod = _sub(det, "prod")
        _sub(prod, "cProd", str(indice))
        _sub(prod, "cEAN", "SEM GTIN")
        _sub(prod, "xProd", f"Produto {indice}")
        _sub(prod, "NCM", ncm)
        _sub(prod, "CFOP", cfop)
        _sub(prod, "uCom", "UN")
        _sub(prod, "qCom", quantidade)
        _sub(prod, "vUnCom", f"{float(valor_item) / float(quantidade):.10f}")
        _sub(prod, "vProd", valor_item)
        _sub(prod, "cEANTrib", "SEM GTIN")
        _sub(prod, "uTrib", "UN")
        _sub(prod, "qTrib", quantidade)
        _sub(prod, "vUnTrib", f"{float(valor_item) / float(quantidade):.10f}")
        _sub(prod, "indTot", "1")

        imposto = _sub(det, "imposto")
        icms = _sub(imposto, "ICMS")
        icms00 = _sub(icms, "ICMS00")
        _sub(icms00, "orig", "0")
        _sub(icms00, "CST", cst)
        _sub(icms00, "modBC", "3")
        _sub(icms00, "vBC", valor_item)
        _sub(icms00, "pICMS", "18.00")
        _sub(icms00, "vICMS", f"{float(valor_item) * 0.18:.2f}")
        pis = _sub(imposto, "PIS")
        pis_aliq = _sub(pis, "PISAliq")
        _sub(pis_aliq, "CST", "01")
        _sub(pis_aliq, "vBC", valor_item)
        _sub(pis_aliq, "pPIS", "1.65")
        _sub(pis_aliq, "vPIS", f"{float(valor_item) * 0.0165:.2f}")
        cofins = _sub(imposto, "COFINS")
        cofins_aliq = _sub(cofins, "COFINSAliq")
        _sub(cofins_aliq, "CST", "01")
        _sub(cofins_aliq, "vBC", valor_item)
        _sub(cofins_aliq, "pCOFINS", "7.60")
        _sub(cofins_aliq, "vCOFINS", f"{float(valor_item) * 0.076:.2f}")

    item(1)
    if dois_itens:
        item(2)

    total_elem = _sub(inf, "total")
    icms_tot = _sub(total_elem, "ICMSTot")
    for tag, valor in (
        ("vBC", total),
        ("vICMS", f"{float(total) * 0.18:.2f}"),
        ("vICMSDeson", "0.00"),
        ("vFCP", "0.00"),
        ("vBCST", "0.00"),
        ("vST", "0.00"),
        ("vFCPST", "0.00"),
        ("vFCPSTRet", "0.00"),
        ("vProd", total),
        ("vFrete", "0.00"),
        ("vSeg", "0.00"),
        ("vDesc", "0.00"),
        ("vII", "0.00"),
        ("vIPI", "0.00"),
        ("vIPIDevol", "0.00"),
        ("vPIS", f"{float(total) * 0.0165:.2f}"),
        ("vCOFINS", f"{float(total) * 0.076:.2f}"),
        ("vOutro", "0.00"),
        ("vNF", total),
    ):
        _sub(icms_tot, tag, valor)

    transp = _sub(inf, "transp")
    _sub(transp, "modFrete", "9")
    # Volumes são opcionais: sem eles a etiqueta não tem o que imprimir. Quando
    # informados, geram `transp/vol` como no leiaute 4.00.
    for volume in volumes or []:
        vol = _sub(transp, "vol")
        if volume.get("qVol"):
            _sub(vol, "qVol", volume["qVol"])
        if volume.get("esp"):
            _sub(vol, "esp", volume["esp"])
        if volume.get("pesoL"):
            _sub(vol, "pesoL", volume["pesoL"])
        if volume.get("pesoB"):
            _sub(vol, "pesoB", volume["pesoB"])
        if volume.get("marca"):
            _sub(vol, "marca", volume["marca"])

    if com_pagamento:
        pag = _sub(inf, "pag")
        det_pag = _sub(pag, "detPag")
        _sub(det_pag, "indPag", "0")
        _sub(det_pag, "tPag", "01")
        _sub(det_pag, "vPag", total)

    if com_assinatura:
        _assinatura(nfe_elem, f"NFe{chave}")

    if com_protocolo:
        protocolo = _sub(raiz, "protNFe", versao="4.00")
        info_prot = _sub(protocolo, "infProt")
        _sub(info_prot, "tpAmb", tp_amb)
        _sub(info_prot, "verAplic", "SP")
        _sub(info_prot, "chNFe", chave)
        _sub(info_prot, "dhRecbto", "2025-01-15T10:31:00-03:00")
        _sub(info_prot, "nProt", "135250000000001")
        _sub(info_prot, "digVal", _VALOR_DIGEST)
        _sub(info_prot, "cStat", "100")
        _sub(info_prot, "xMotivo", "Autorizado o uso da NF-e")

    return para_bytes(raiz)


# ----------------------------------------------------------------------
# CT-e
# ----------------------------------------------------------------------
def cte(
    *,
    c_uf: str = "35",
    aamm: str = "2501",
    serie: str = "1",
    numero: str = "456",
    c_ct: str = "12345678",
    valor: str = "1500.00",
    com_assinatura: bool = True,
    com_protocolo: bool = True,
    cfop: str = "5353",
    cnpj_emitente: str = CNPJ_EMITENTE,
) -> bytes:
    """Constrói um CT-e 4.00 sintético, por padrão autoconsistente."""
    chave = montar_chave(
        c_uf=c_uf,
        aamm=aamm,
        cnpj=cnpj_emitente,
        modelo="57",
        serie=serie,
        numero=numero,
        tp_emis="1",
        c_nf=c_ct,
    )

    raiz = ET.Element("cteProc", {"versao": "4.00", "xmlns": NS_CTE})
    cte_elem = _sub(raiz, "CTe")
    inf = _sub(cte_elem, "infCte", versao="4.00", Id=f"CTe{chave}")

    ide = _sub(inf, "ide")
    _sub(ide, "cUF", c_uf)
    _sub(ide, "cCT", c_ct)
    _sub(ide, "CFOP", cfop)
    _sub(ide, "natOp", "Prestacao de servico de transporte")
    _sub(ide, "mod", "57")
    _sub(ide, "serie", serie)
    _sub(ide, "nCT", numero)
    _sub(ide, "dhEmi", "2025-01-20T09:00:00-03:00")
    _sub(ide, "tpImp", "1")
    _sub(ide, "tpEmis", "1")
    _sub(ide, "cDV", chave[-1])
    _sub(ide, "tpAmb", "1")
    _sub(ide, "tpCTe", "0")
    _sub(ide, "procEmi", "0")
    _sub(ide, "verProc", "notasbr-teste")
    _sub(ide, "cMunEnv", "3550308")
    _sub(ide, "xMunEnv", "Sao Paulo")
    _sub(ide, "UFEnv", "SP")
    _sub(ide, "modal", "01")
    _sub(ide, "tpServ", "0")
    _sub(ide, "cMunIni", "3550308")
    _sub(ide, "xMunIni", "Sao Paulo")
    _sub(ide, "UFIni", "SP")
    _sub(ide, "cMunFim", "3304557")
    _sub(ide, "xMunFim", "Rio de Janeiro")
    _sub(ide, "UFFim", "RJ")
    _sub(ide, "retira", "1")
    _sub(ide, "indIEToma", "1")

    emit = _sub(inf, "emit")
    _sub(emit, "CNPJ", cnpj_emitente)
    _sub(emit, "IE", "111111111111")
    _sub(emit, "xNome", "Transportadora Exemplo LTDA")
    _endereco(_sub(emit, "enderEmit"), "SP")

    rem = _sub(inf, "rem")
    _sub(rem, "CNPJ", CNPJ_DESTINATARIO)
    _sub(rem, "xNome", "Remetente Exemplo")
    _endereco(_sub(rem, "enderReme"), "SP")
    _sub(rem, "IE", "222222222222")

    dest = _sub(inf, "dest")
    _sub(dest, "CNPJ", CNPJ_DESTINATARIO)
    _sub(dest, "xNome", "Destinatario Exemplo")
    _endereco(_sub(dest, "enderDest"), "RJ", "3304557", "Rio de Janeiro")
    _sub(dest, "IE", "333333333333")

    prest = _sub(inf, "vPrest")
    _sub(prest, "vTPrest", valor)
    _sub(prest, "vRec", valor)
    componente = _sub(prest, "Comp")
    _sub(componente, "xNome", "Frete peso")
    _sub(componente, "vComp", valor)

    imp = _sub(inf, "imp")
    icms = _sub(imp, "ICMS")
    icms00 = _sub(icms, "ICMS00")
    _sub(icms00, "CST", "00")
    _sub(icms00, "vBC", valor)
    _sub(icms00, "pICMS", "12.00")
    _sub(icms00, "vICMS", f"{float(valor) * 0.12:.2f}")
    _sub(imp, "vTotTrib", "0.00")

    norm = _sub(inf, "infCTeNorm")
    carga = _sub(norm, "infCarga")
    _sub(carga, "vCarga", "10000.00")
    _sub(carga, "proPred", "Mercadoria")
    inf_doc = _sub(norm, "infDoc")
    inf_nfe = _sub(inf_doc, "infNFe")
    _sub(
        inf_nfe,
        "chave",
        montar_chave(
            c_uf="35",
            aamm="2501",
            cnpj=CNPJ_DESTINATARIO,
            modelo="55",
            serie="1",
            numero="999",
            tp_emis="1",
            c_nf="87654321",
        ),
    )

    if com_assinatura:
        _assinatura(cte_elem, f"CTe{chave}")

    if com_protocolo:
        protocolo = _sub(raiz, "protCTe", versao="4.00")
        info_prot = _sub(protocolo, "infProt")
        _sub(info_prot, "tpAmb", "1")
        _sub(info_prot, "chCTe", chave)
        _sub(info_prot, "dhRecbto", "2025-01-20T09:05:00-03:00")
        _sub(info_prot, "nProt", "135250000000002")
        _sub(info_prot, "cStat", "100")
        _sub(info_prot, "xMotivo", "Autorizado o uso do CT-e")

    return para_bytes(raiz)


# ----------------------------------------------------------------------
# MDF-e
# ----------------------------------------------------------------------
NS_MDFE = "http://www.portalfiscal.inf.br/mdfe"


def mdfe(
    *,
    c_uf: str = "35",
    aamm: str = "2501",
    serie: str = "1",
    numero: str = "77",
    c_mdf: str = "87654321",
    modal: str = "1",
    placa: str = "ABC1D23",
    chaves_cte: tuple[str, ...] | None = None,
    com_protocolo: bool = True,
) -> bytes:
    """Constrói um MDF-e 3.00 sintético.

    **Marcado [A VALIDAR]**: diferente de NF-e (4.00) e CT-e (4.00), não há XSD de
    MDF-e na base de referência local. O layout aqui segue o 3.00 de conhecimento
    geral (ide/emit/infModal/infDoc/tot) e precisa ser conferido contra o XSD
    oficial antes de uso em produção.
    """
    chave = montar_chave(
        c_uf=c_uf,
        aamm=aamm,
        cnpj=CNPJ_EMITENTE,
        modelo="58",
        serie=serie,
        numero=numero,
        tp_emis="1",
        c_nf=c_mdf,
    )

    raiz = ET.Element("mdfeProc", {"versao": "3.00", "xmlns": NS_MDFE})
    mdfe_elem = _sub(raiz, "MDFe")
    inf = _sub(mdfe_elem, "infMDFe", versao="3.00", Id=f"MDFe{chave}")

    ide = _sub(inf, "ide")
    _sub(ide, "cUF", c_uf)
    _sub(ide, "cDF", c_mdf)
    _sub(ide, "mod", "58")
    _sub(ide, "serie", serie)
    _sub(ide, "nMDF", numero)
    _sub(ide, "cMDF", c_mdf)
    _sub(ide, "cDV", chave[-1])
    _sub(ide, "dhEmi", "2025-01-21T08:00:00-03:00")
    _sub(ide, "tpEmis", "1")
    _sub(ide, "tpAmb", "1")
    _sub(ide, "tpTransp", "1")
    _sub(ide, "modTransp", modal)
    _sub(ide, "UFIni", "SP")
    _sub(ide, "UFFim", "RJ")
    # Os municípios e UFs ficam DENTRO dos grupos, não como irmãos deles.
    mun_carrega = _sub(ide, "infMunCarrega")
    _sub(mun_carrega, "cMunCarrega", "3550308")
    _sub(mun_carrega, "xMunCarrega", "Sao Paulo")
    percurso = _sub(ide, "infPercurso")
    _sub(percurso, "UFPerc", "MG")

    emit = _sub(inf, "emit")
    _sub(emit, "CNPJ", CNPJ_EMITENTE)
    _sub(emit, "IE", "111111111111")
    _sub(emit, "xNome", "Transportadora Exemplo LTDA")
    _endereco(_sub(emit, "enderEmit"), "SP")

    modal_elem = _sub(inf, "infModal", versaoModal="3.00")
    rodo = _sub(modal_elem, "rodo")
    _sub(rodo, "placa", placa)
    _sub(rodo, "tara", "8500")
    _sub(rodo, "capKG", "25000")
    _sub(rodo, "capM3", "60")

    doc = _sub(inf, "infDoc")
    mun = _sub(doc, "infMunDescarga")
    _sub(mun, "cMunDescarga", "3304557")
    _sub(mun, "xMunDescarga", "Rio de Janeiro")
    for chcte in chaves_cte or (
        montar_chave(
            c_uf="35",
            aamm="2501",
            cnpj=CNPJ_EMITENTE,
            modelo="57",
            serie="1",
            numero="456",
            tp_emis="1",
            c_nf="12345678",
        ),
    ):
        inf_cte = _sub(mun, "infCTe")
        _sub(inf_cte, "chCTe", chcte)

    tot = _sub(inf, "tot")
    _sub(tot, "qCTe", str(len(chaves_cte or (1,))))
    _sub(tot, "qNFe", "1")
    _sub(tot, "vCarga", "10000.00")
    _sub(tot, "cUnid", "01")
    _sub(tot, "qCarga", "15000.0000")

    if com_protocolo:
        protocolo = _sub(raiz, "protMDFe", versao="3.00")
        info_prot = _sub(protocolo, "infProt")
        _sub(info_prot, "tpAmb", "1")
        _sub(info_prot, "chMDFe", chave)
        _sub(info_prot, "dhRecbto", "2025-01-21T08:05:00-03:00")
        _sub(info_prot, "nProt", "135250000000003")
        _sub(info_prot, "cStat", "100")
        _sub(info_prot, "xMotivo", "Autorizado o uso do MDF-e")

    return para_bytes(raiz)
