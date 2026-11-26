"""Envelope do lote (`enviNFe`) e consulta de status (`consStatServ`).

Ambos foram escritos a partir do **PL_010h** e são validados contra o schema oficial
nos testes. Eles são a parte que pode ser construída e verificada **sem** o
webservice: a chamada SOAP depende de credenciamento na SEFAZ da UF, mas o XML que
seria enviado já é verificável.

Estrutura confirmada no schema:

    TEnviNFe    -> idLote (1) + indSinc (1) + NFe (1..N)
    TConsStatServ -> tpAmb (1) + cUF (1) + xServ (1)

`indSinc`: 1 = processamento síncrono (resposta imediata, até 50 notas); 0 = lote
assíncrono, que exige `consReciNFe` com o `recibo`.
"""

from __future__ import annotations

import re

from lxml import etree

from app.nfe.base import NS_NFE, VERSAO, ErroDeNFe, _codigo_uf

NS = f"{{{NS_NFE}}}"

#: Limite do modo síncrono documentado pela SEFAZ. Acima disso o lote é assíncrono.
LIMITE_SINCRONO = 50
#: Lote aceita até 50 notas por envio, independente do modo.
LIMITE_POR_LOTE = 50


def montar_enviNFe(
    notas_assinadas: list[bytes],
    *,
    id_lote: str | int = "1",
    sincrono: bool = True,
) -> bytes:
    """Monta o envelope do lote com as NF-e já assinadas.

    As notas **precisam** vir assinadas: a SEFAZ recusa lote com NFe sem assinatura,
    e o schema do envelope também exige o grupo `Signature`.
    """
    if not notas_assinadas:
        raise ErroDeNFe("o lote precisa de ao menos uma NF-e")
    if len(notas_assinadas) > LIMITE_POR_LOTE:
        raise ErroDeNFe(
            f"o lote aceita no máximo {LIMITE_POR_LOTE} NF-e; recebeu {len(notas_assinadas)}"
        )
    if sincrono and len(notas_assinadas) > LIMITE_SINCRONO:
        raise ErroDeNFe(
            f"processamento síncrono aceita até {LIMITE_SINCRONO} NF-e; "
            "use sincrono=False e consulte o recibo"
        )

    identificador = str(id_lote)
    if not re.fullmatch(r"\d{1,15}", identificador):
        raise ErroDeNFe("idLote deve ter de 1 a 15 dígitos")

    raiz = etree.Element(f"{NS}enviNFe", nsmap={None: NS_NFE})
    raiz.set("versao", VERSAO)
    etree.SubElement(raiz, f"{NS}idLote").text = identificador
    etree.SubElement(raiz, f"{NS}indSinc").text = "1" if sincrono else "0"

    for bruta in notas_assinadas:
        try:
            nota = etree.fromstring(bruta)
        except etree.XMLSyntaxError as exc:
            raise ErroDeNFe(f"NF-e do lote não é XML válido: {exc}") from exc
        if etree.QName(nota).localname != "NFe":
            raise ErroDeNFe(f"o lote espera elementos NFe; recebeu {etree.QName(nota).localname}")
        raiz.append(nota)

    return b'<?xml version="1.0" encoding="UTF-8"?>' + etree.tostring(raiz)


def montar_consStatServ(*, uf: str, ambiente: str = "2") -> bytes:
    """Monta a consulta de status do serviço da UF.

    É a chamada mais barata para saber se o webservice está no ar e se o certificado
    é aceito — por isso é a primeira coisa a tentar quando há credenciamento.
    """
    if ambiente not in ("1", "2"):
        raise ErroDeNFe("tpAmb deve ser '1' (produção) ou '2' (homologação)")

    raiz = etree.Element(f"{NS}consStatServ", nsmap={None: NS_NFE})
    raiz.set("versao", VERSAO)
    etree.SubElement(raiz, f"{NS}tpAmb").text = ambiente
    etree.SubElement(raiz, f"{NS}cUF").text = _codigo_uf(uf)
    etree.SubElement(raiz, f"{NS}xServ").text = "STATUS"
    return b'<?xml version="1.0" encoding="UTF-8"?>' + etree.tostring(raiz)


def interpretar_retorno_status(xml: bytes) -> dict[str, str | None]:
    """Lê o `retConsStatServ` da SEFAZ.

    `cStat` 107 significa "serviço em operação"; 108, "paralisado momentaneamente";
    109, "paralisado sem previsão". O retorno é **dado do serviço**, não nosso.
    """
    try:
        raiz = etree.fromstring(xml)
    except etree.XMLSyntaxError as exc:
        raise ErroDeNFe(f"resposta da SEFAZ não é XML: {exc}") from exc

    def _texto(tag: str) -> str | None:
        elemento = raiz.find(f".//{NS}{tag}")
        return elemento.text if elemento is not None else None

    return {
        "cStat": _texto("cStat"),
        "xMotivo": _texto("xMotivo"),
        "cUF": _texto("cUF"),
        "dhRecbto": _texto("dhRecbto"),
        "tMed": _texto("tMed"),
    }
