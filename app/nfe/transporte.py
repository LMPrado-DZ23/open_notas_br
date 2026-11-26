"""Cliente SOAP da SEFAZ com transporte injetável.

O transporte é uma interface, não `httpx` direto. Motivo: sem isso não há como testar o
cliente — e o que não é testado vira surpresa em produção. Em teste, um transporte falso
devolve respostas reais do leiaute; em produção, o transporte HTTP real entra no lugar.

**Nenhuma URL aqui.** O endpoint vem da tabela `webservices_sefaz` (R3) e é parâmetro.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from lxml import etree

from app.nfe.soap import ErroSOAP, desenvelopar, envelopar, extrair_falha


class ErroTransporte(Exception):
    """Falha de transporte: timeout, conexão, 5xx. **Transitória**."""


class ErroSefazDefinitivo(Exception):
    """A SEFAZ respondeu e recusou (Fault ou cStat de rejeição). **Não retentar**."""


class TransporteSOAP(Protocol):
    """Contrato mínimo de transporte. Implementado por HTTP real e por dublê de teste."""

    async def enviar(self, *, url: str, corpo: bytes, timeout_s: float) -> bytes: ...


@dataclass(frozen=True, slots=True)
class RespostaSefaz:
    """Resposta já desenvelopada, com o XML cru preservado para auditoria."""

    xml: bytes
    elemento: etree._Element

    def texto(self, tag: str) -> str | None:
        alvo = self.elemento.find(f".//{{http://www.portalfiscal.inf.br/nfe}}{tag}")
        return alvo.text if alvo is not None else None

    @property
    def cstat(self) -> str | None:
        return self.texto("cStat")


class ClienteSefaz:
    """Envia o XML fiscal e devolve a resposta desenvelopada."""

    def __init__(self, transporte: TransporteSOAP, *, timeout_s: float = 30.0) -> None:
        self._transporte = transporte
        self._timeout = timeout_s

    async def chamar(
        self, *, url: str, xml_fiscal: bytes, timeout_s: float | None = None
    ) -> RespostaSefaz:
        if not url.startswith("https://"):
            # R3: serviço fiscal em http é dado e credencial em texto claro.
            raise ValueError("URL de webservice precisa ser https")

        envelope = envelopar(xml_fiscal)

        try:
            bruto = await self._transporte.enviar(
                url=url, corpo=envelope, timeout_s=timeout_s or self._timeout
            )
        except (TimeoutError, OSError, ConnectionError) as exc:
            raise ErroTransporte(str(exc)) from exc

        falha = extrair_falha(bruto)
        if falha is not None:
            raise ErroSefazDefinitivo(
                f"SOAP Fault {falha.get('code', '')}: {falha.get('reason', '')}".strip()
            )

        try:
            elemento = desenvelopar(bruto)
        except ErroSOAP as exc:
            # Body ausente/HTML de gateway: para o cliente é falha de transporte, e é
            # transitória — o serviço pode voltar.
            raise ErroTransporte(f"resposta inesperada: {exc}") from exc

        return RespostaSefaz(xml=bruto, elemento=elemento)
