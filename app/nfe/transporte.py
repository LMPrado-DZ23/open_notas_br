"""Cliente SOAP da SEFAZ com transporte injetável.

O transporte é uma interface, não `httpx` direto. Motivo: sem isso não há como testar o
cliente — e o que não é testado vira surpresa em produção. Em teste, um transporte falso
devolve respostas reais do leiaute; em produção, o transporte HTTP real entra no lugar.

**Nenhuma URL aqui.** O endpoint vem da tabela `webservices_sefaz` (R3) e é parâmetro.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

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

    @property
    def xml_fiscal(self) -> bytes:
        """O elemento fiscal serializado, sem o envelope SOAP.

        `xml` é a resposta bruta (para auditoria); `xml_fiscal` é o que os leitores de
        leiaute esperam. Confundir os dois fazia `ler()` recusar a resposta com
        "elemento não é retorno da SEFAZ: Envelope".
        """
        return etree.tostring(self.elemento)


class ClienteSefaz:
    """Envia o XML fiscal e devolve a resposta desenvelopada."""

    def __init__(self, transporte: TransporteSOAP, *, timeout_s: float = 30.0) -> None:
        self._transporte = transporte
        self._timeout = timeout_s

    async def chamar(
        self,
        *,
        url: str,
        xml_fiscal: bytes,
        timeout_s: float | None = None,
        ns_servico: str | None = None,
        soap_versao: str = "1.2",
    ) -> RespostaSefaz:
        if not url.startswith("https://"):
            # R3: serviço fiscal em http é dado e credencial em texto claro.
            raise ValueError("URL de webservice precisa ser https")

        envelope = envelopar(xml_fiscal, ns_servico=ns_servico, soap_versao=soap_versao)

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


class TransporteHTTP:
    """Transporte HTTP com mTLS, para produção.

    Testado contra servidor ASGI local (sem rede, sem certificado real): o que se verifica
    aqui é o **contrato do pedido** — método, `Content-Type`, `SOAPAction` e corpo — e a
    tradução de status para erro transitório.

    O certificado é injetado como caminho de arquivo PKCS#12 convertido em PEM temporário
    pelo chamador; este módulo não lê PFX nem conhece senha (R4).
    """

    def __init__(
        self,
        *,
        cert_pem: str | None = None,
        key_pem: str | None = None,
        cliente: Any = None,
        soap_action: str = "",
        soap_versao: str = "1.2",
    ) -> None:
        # `cliente` permite injetar um `httpx.AsyncClient` já configurado (teste).
        self._cert = (cert_pem, key_pem) if cert_pem and key_pem else None
        self._cliente = cliente
        # Os endpoints `.asmx` do SVRS/SEFAZ-SP exigem a `action` do serviço; sem ela respondem
        # HTTP 500 ao mesmo XML que GO aceita. O valor vem do WSDL oficial de cada serviço
        # (`soap12:operation soapAction=...`), nunca de chute.
        self._soap_action = soap_action
        # SOAP 1.2 usa `application/soap+xml` com a action no Content-Type; SOAP 1.1 usa
        # `text/xml` com a action no header `SOAPAction`. Endpoints `.asmx` do SVRS exigem 1.1.
        self._soap_versao = soap_versao

    async def enviar(self, *, url: str, corpo: bytes, timeout_s: float) -> bytes:
        import httpx

        if self._soap_versao == "1.1":
            # SOAP 1.1: `text/xml` e a action vai no header `SOAPAction`. Medido: o SVRS
            # responde "media type is unsupported" a quem manda `application/soap+xml` com
            # envelope 1.1.
            cabecalhos = {
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f'"{self._soap_action}"',
                "Accept": "text/xml",
            }
        else:
            cabecalhos = {
                "Content-Type": (
                    f'application/soap+xml; charset=utf-8; action="{self._soap_action}"'
                ),
                "Accept": "application/soap+xml",
            }

        if self._cliente is not None:
            resposta = await self._cliente.post(url, content=corpo, headers=cabecalhos)
        else:
            async with httpx.AsyncClient(
                timeout=timeout_s, cert=self._cert, verify=True
            ) as cliente:
                resposta = await cliente.post(url, content=corpo, headers=cabecalhos)

        if resposta.status_code >= 500:
            # 5xx é transitório: o serviço pode voltar. 4xx de gateway também, mas 4xx de
            # contrato é erro nosso — devolvemos o corpo para o erro ficar diagnosticável.
            raise ErroTransporte(f"HTTP {resposta.status_code}")

        return resposta.content
