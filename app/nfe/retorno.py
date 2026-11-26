"""Leitura do retorno da SEFAZ para lote e autorização.

Extrai estrutura, não interpreta regra. Os campos vêm do leiaute (`retEnviNFe`,
`retConsReciNFe`, `protNFe`); **o significado dos códigos `cStat` é do MOC**, e este
módulo não decide se um código "é sucesso" por conta própria fora dos casos que a
documentação oficial descreve de forma inequívoca.

Princípio: se o código não é conhecido, o retorno é `indefinido` — não `autorizado` nem
`rejeitado`. Chutar aqui significa dizer ao lojista que a nota foi autorizada quando ela
não foi, ou o contrário.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from lxml import etree

from app.nfe.lote import NS

#: `cStat` do protocolo de autorização. 100 = "Autorizado o uso da NF-e" (MOC).
CSTAT_AUTORIZADA = "100"
#: `cStat` de lote recebido (assíncrono) e de lote já processado.
CSTAT_LOTE_RECEBIDO = "103"
CSTAT_LOTE_PROCESSADO = "104"
#: `cStat` de denegação — a nota **existe** e foi recusada; não é erro de transporte.
CSTAT_DENEGADA = "110"


class Situacao(StrEnum):
    AUTORIZADA = "autorizada"
    DENEGADA = "denegada"
    LOTE_RECEBIDO = "lote_recebido"
    LOTE_PROCESSADO = "lote_processado"
    REJEITADA = "rejeitada"
    INDEFINIDA = "indefinida"


@dataclass(frozen=True, slots=True)
class Protocolo:
    """`protNFe` — a prova de autorização de uma nota."""

    chave: str | None
    cstat: str | None
    xmotivo: str | None
    numero_protocolo: str | None
    data_recebimento: str | None

    @property
    def autorizada(self) -> bool:
        return self.cstat == CSTAT_AUTORIZADA


@dataclass(frozen=True, slots=True)
class Retorno:
    """Resultado estruturado de um lote, recibo ou consulta."""

    cstat: str | None
    xmotivo: str | None
    recibo: str | None = None
    protocolos: tuple[Protocolo, ...] = field(default_factory=tuple)
    xml: bytes = b""

    @property
    def situacao(self) -> Situacao:
        # O protocolo de cada nota manda: o `cStat` do lote diz "processado", não
        # "autorizada". Confundir os dois é o erro clássico deste fluxo.
        if any(p.autorizada for p in self.protocolos):
            return Situacao.AUTORIZADA
        if any(p.cstat == CSTAT_DENEGADA for p in self.protocolos):
            return Situacao.DENEGADA
        # Tem protocolo e nenhum é autorizado nem denegado => rejeição da nota.
        # Este ramo precisa vir ANTES do cStat do lote: senão `104` (lote processado)
        # captura e a nota rejeitada apareceria como "processada".
        if self.protocolos:
            return Situacao.REJEITADA
        if self.cstat == CSTAT_LOTE_RECEBIDO:
            return Situacao.LOTE_RECEBIDO
        if self.cstat == CSTAT_LOTE_PROCESSADO:
            return Situacao.LOTE_PROCESSADO
        if self.cstat:
            return Situacao.REJEITADA
        return Situacao.INDEFINIDA

    @property
    def autorizada(self) -> bool:
        return self.situacao is Situacao.AUTORIZADA


class ErroDeRetorno(Exception):
    """XML de retorno malformado ou sem estrutura reconhecível."""


def _texto(raiz: etree._Element, tag: str) -> str | None:
    alvo = raiz.find(f".//{NS}{tag}")
    return alvo.text.strip() if alvo is not None and alvo.text else None


def ler(xml: bytes) -> Retorno:
    """Lê `retEnviNFe`, `retConsReciNFe` ou `retConsSitNFe`."""
    try:
        raiz = etree.fromstring(xml)
    except etree.XMLSyntaxError as exc:
        raise ErroDeRetorno(f"XML inválido: {exc}") from exc

    nome = etree.QName(raiz).localname
    if nome not in ("retEnviNFe", "retConsReciNFe", "retConsSitNFe", "retConsStatServ"):
        raise ErroDeRetorno(f"elemento não é retorno da SEFAZ: {nome}")

    protocolos = tuple(
        Protocolo(
            chave=_texto(prot, "chNFe"),
            cstat=_texto(prot, "cStat"),
            xmotivo=_texto(prot, "xMotivo"),
            numero_protocolo=_texto(prot, "nProt"),
            data_recebimento=_texto(prot, "dhRecbto"),
        )
        for prot in raiz.findall(f".//{NS}protNFe")
    )

    return Retorno(
        cstat=_texto(raiz, "cStat"),
        xmotivo=_texto(raiz, "xMotivo"),
        recibo=_texto(raiz, "nRecibo"),
        protocolos=protocolos,
        xml=xml,
    )
