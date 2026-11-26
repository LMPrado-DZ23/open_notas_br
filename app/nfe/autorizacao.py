"""Ciclo de autorização do lote: enviar → (recibo →) protocolo.

Compõe as peças já testadas (`envelopar`, `ClienteSefaz`, `ler`) numa máquina de estados
pequena. **Testável com transporte falso**: o que se verifica aqui é a sequência e a
decisão, não a rede.

A sequência não é escolha nossa, é do leiaute:

- resposta com `protNFe` (síncrono) → já temos o protocolo, acabou
- resposta com `cStat 103` → lote recebido, devolve `nRecibo`; é preciso consultar o
  recibo depois
- qualquer outra coisa → rejeição, e **não** se insiste

Insistir num recibo que a SEFAZ rejeitou gastaria cota e não mudaria o resultado.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.nfe.retorno import Retorno, Situacao, ler
from app.nfe.transporte import ClienteSefaz, ErroSefazDefinitivo


class ErroDeAutorizacao(Exception):
    """O lote não pôde ser autorizado nesta tentativa."""


@dataclass(frozen=True, slots=True)
class ResultadoAutorizacao:
    """Estado final de uma tentativa de autorização."""

    situacao: Situacao
    retorno: Retorno
    #: Presente quando a SEFAZ respondeu 103: consultar depois com este recibo.
    recibo: str | None = None

    @property
    def autorizada(self) -> bool:
        return self.situacao is Situacao.AUTORIZADA

    @property
    def precisa_consultar_recibo(self) -> bool:
        return self.situacao is Situacao.LOTE_RECEBIDO and bool(self.recibo)

    @property
    def protocolo(self):
        """O protocolo da primeira nota autorizada, se houver."""
        for prot in self.retorno.protocolos:
            if prot.autorizada:
                return prot
        return None


async def enviar_lote(cliente: ClienteSefaz, *, url: str, xml_lote: bytes) -> ResultadoAutorizacao:
    """Envia o lote e classifica a resposta. Não consulta recibo."""
    try:
        resposta = await cliente.chamar(url=url, xml_fiscal=xml_lote)
    except ErroSefazDefinitivo as exc:
        # Fault é definitivo: não há o que consultar depois.
        raise ErroDeAutorizacao(f"SEFAZ recusou o envelope: {exc}") from exc

    retorno = ler(resposta.xml_fiscal)
    return ResultadoAutorizacao(situacao=retorno.situacao, retorno=retorno, recibo=retorno.recibo)


async def consultar_recibo(
    cliente: ClienteSefaz, *, url: str, xml_consulta: bytes
) -> ResultadoAutorizacao:
    """Consulta o recibo de um lote assíncrono."""
    try:
        resposta = await cliente.chamar(url=url, xml_fiscal=xml_consulta)
    except ErroSefazDefinitivo as exc:
        raise ErroDeAutorizacao(f"SEFAZ recusou a consulta: {exc}") from exc

    retorno = ler(resposta.xml_fiscal)
    return ResultadoAutorizacao(situacao=retorno.situacao, retorno=retorno)


async def autorizar(
    cliente: ClienteSefaz,
    *,
    url_envio: str,
    url_recibo: str,
    xml_lote: bytes,
    montar_consulta,
    tentativas_recibo: int = 1,
) -> ResultadoAutorizacao:
    """Envia e, se a SEFAZ responder 103, consulta o recibo.

    `montar_consulta(recibo) -> bytes` monta o `consNRecNFe`. Recebido por parâmetro
    porque a montagem depende do leiaute, não do ciclo.

    `tentativas_recibo=1` por padrão: cada consulta consome cota da SEFAZ e o intervalo
    mínimo é regulado. Repetir em laço aqui seria abuso; quem precisa esperar, espera fora.
    """
    envio = await enviar_lote(cliente, url=url_envio, xml_lote=xml_lote)

    if not envio.precisa_consultar_recibo:
        return envio

    recibo = envio.recibo
    assert recibo is not None  # garantido por `precisa_consultar_recibo`
    ultima = envio
    for _ in range(tentativas_recibo):
        ultima = await consultar_recibo(
            cliente, url=url_recibo, xml_consulta=montar_consulta(recibo)
        )
        if ultima.situacao is not Situacao.LOTE_RECEBIDO:
            break
    return ultima
