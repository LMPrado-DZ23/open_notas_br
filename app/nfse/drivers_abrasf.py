"""Driver base ABRASF: motor parametrizável, sem URL fixa.

O ponto central: **nenhuma URL aqui**. Endpoint, namespace, versão de SOAP e encoding vêm
do registro do município (`municipios_nfse`), que carrega `fonte_url`. Este módulo só monta
e desmonta a mensagem.

Por isso ele pode ser escrito e testado sem credenciamento: o que se verifica é o contrato
do envelope, a seleção de encoding e a tradução de resposta — não a rede.

Assinatura: **seletiva**, como o leiaute prevê. `assina_rps` e `assina_lote` são
independentes; firmar os dois quando o provedor espera um só produz lote recusado.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from lxml import etree

from app.nfse.drivers import CategoriaErro, ResultadoDriver

NS_SOAP11 = "http://schemas.xmlsoap.org/soap/envelope/"
NS_SOAP12 = "http://www.w3.org/2003/05/soap-envelope"


class ErroAbrasf(Exception):
    """Mensagem ABRASF malformada ou sem estrutura reconhecível."""


class TransporteProvedor(Protocol):
    """Transporte SOAP do provedor municipal. Injetado."""

    async def enviar(self, *, url: str, corpo: bytes, encoding: str) -> bytes: ...


@dataclass(frozen=True, slots=True)
class ConfiguracaoAbrasf:
    """O que varia por município. Vem do cadastro, nunca do código."""

    url: str
    namespace: str
    versao_soap: str = "1.2"
    encoding: str = "UTF-8"
    assina_rps: bool = True
    assina_lote: bool = True


def _namespace_soap(versao: str) -> str:
    if versao not in ("1.1", "1.2"):
        raise ErroAbrasf(f"versão de SOAP desconhecida: {versao}")
    return NS_SOAP11 if versao == "1.1" else NS_SOAP12


def envelopar(
    xml_fiscal: bytes, *, namespace: str, versao_soap: str = "1.2", encoding: str = "UTF-8"
) -> bytes:
    """Embrulha o XML do RPS/lote num envelope SOAP do provedor.

    O nome do elemento no `Body` (`EnviarLoteRpsEnvio`, `ConsultarLoteRpsEnvio`...) já vem
    no XML fiscal; aqui só se embrulha, sem renomear — renomear quebraria o leiaute.
    """
    ns_soap = _namespace_soap(versao_soap)

    try:
        dados = etree.fromstring(xml_fiscal)
    except etree.XMLSyntaxError as exc:
        raise ErroAbrasf(f"XML fiscal inválido: {exc}") from exc

    envelope = etree.Element(f"{{{ns_soap}}}Envelope", nsmap={"soap": ns_soap, "nfe": namespace})
    corpo = etree.SubElement(envelope, f"{{{ns_soap}}}Body")
    corpo.append(dados)

    # Uma única declaração, a do próprio lxml. Antes o código prependava uma declaração e o
    # `tostring(..., encoding=...)` emitia outra: em ISO-8859-1 (GINFES/DSF legados) saíam
    # **duas** declarações e o envelope era XML malformado — `XML declaration allowed only at
    # the start of the document`. Em UTF-8 passava porque `tostring` não declara por padrão.
    return etree.tostring(envelope, encoding=encoding, xml_declaration=True)


def desenvelopar(
    resposta: bytes, *, versao_soap: str = "1.2", encoding: str = "UTF-8"
) -> etree._Element:
    """Devolve o primeiro elemento do `Body`, já como árvore."""
    ns_soap = _namespace_soap(versao_soap)
    try:
        raiz = etree.fromstring(resposta)
    except etree.XMLSyntaxError:
        # Provedor legado pode responder com encoding declarado diferente do real.
        try:
            raiz = etree.fromstring(resposta.decode(encoding, errors="replace").encode())
        except etree.XMLSyntaxError as exc:
            raise ErroAbrasf(f"resposta não é XML: {exc}") from exc

    corpo = raiz.find(f".//{{{ns_soap}}}Body")
    if corpo is None or len(corpo) == 0:
        raise ErroAbrasf("resposta sem Body SOAP")
    return corpo[0]


def _texto(raiz: etree._Element, tag: str) -> str | None:
    alvo = raiz.find(f".//{tag}")
    if alvo is None:
        alvo = raiz.find(f".//{{*}}{tag}")
    return alvo.text.strip() if alvo is not None and alvo.text else None


#: Código de "lote recebido com sucesso" no retorno ABRASF. [A VALIDAR] por provedor.
LISTA_MENSAGENS_SUCESSO = frozenset({"1", "2"})


def interpretar(
    resposta: bytes, *, versao_soap: str = "1.2", encoding: str = "UTF-8"
) -> ResultadoDriver:
    """Traduz o retorno ABRASF para `ResultadoDriver`.

    A decisão de sucesso é pelo **primeiro** `ListaMensagemRetorno`, não pela ausência de
    erro: provedor legado pode devolver `200` com erro no corpo.
    """
    try:
        raiz = desenvelopar(resposta, versao_soap=versao_soap, encoding=encoding)
    except ErroAbrasf as exc:
        return ResultadoDriver(
            sucesso=False,
            mensagem=str(exc),
            xml_retorno=resposta,
            erro_categoria=CategoriaErro.MUNICIPIO,
        )

    codigo = _texto(raiz, "Codigo")
    mensagem = _texto(raiz, "Mensagem")

    if codigo is not None:
        sucesso = codigo in LISTA_MENSAGENS_SUCESSO
        return ResultadoDriver(
            sucesso=sucesso,
            codigo=codigo,
            mensagem=mensagem,
            xml_retorno=resposta,
            protocolo=_texto(raiz, "Protocolo"),
            numero_nfse=_texto(raiz, "Numero"),
            link_nfse=_texto(raiz, "Link"),
            erro_categoria=None if sucesso else CategoriaErro.MUNICIPIO,
        )

    # Sem `ListaMensagemRetorno`: assume estrutura de sucesso (lote/NFSe presentes).
    return ResultadoDriver(
        sucesso=True,
        xml_retorno=resposta,
        protocolo=_texto(raiz, "Protocolo"),
        numero_nfse=_texto(raiz, "Numero"),
    )


class AbrasfBaseDriver:
    """Motor parametrizável. Subclasses sobrescrevem só o que difere."""

    nome = "abrasf"

    def __init__(
        self,
        *,
        configuracao: ConfiguracaoAbrasf,
        transporte: TransporteProvedor,
        assinador: Callable[[bytes], Awaitable[bytes]] | None = None,
    ) -> None:
        if not configuracao.url.startswith("https://"):
            raise ValueError("URL de provedor precisa ser https")
        self._conf = configuracao
        self._transporte = transporte
        self._assinador = assinador

    async def _chamar(self, xml: bytes, *, assinar: bool) -> ResultadoDriver:
        corpo = xml
        if assinar:
            if self._assinador is None:
                return ResultadoDriver(
                    sucesso=False,
                    mensagem=(
                        "provedor exige assinatura seletiva, mas nenhum assinador foi injetado"
                    ),
                    erro_categoria=CategoriaErro.INTERNO,
                )
            corpo = await self._assinador(xml)

        envelope = envelopar(
            corpo,
            namespace=self._conf.namespace,
            versao_soap=self._conf.versao_soap,
            encoding=self._conf.encoding,
        )
        resposta = await self._transporte.enviar(
            url=self._conf.url, corpo=envelope, encoding=self._conf.encoding
        )
        return interpretar(
            resposta, versao_soap=self._conf.versao_soap, encoding=self._conf.encoding
        )

    async def emitir_rps(self, *, dados: dict[str, Any]) -> ResultadoDriver:
        """`dados["xml"]` já é o RPS/lote montado; aqui só se assina e envia."""
        xml = dados.get("xml")
        if not isinstance(xml, (bytes, bytearray)):
            return ResultadoDriver(
                sucesso=False,
                mensagem="emitir_rps exige dados['xml'] em bytes",
                erro_categoria=CategoriaErro.VALIDACAO,
            )
        return await self._chamar(bytes(xml), assinar=self._conf.assina_lote)

    async def consultar_lote(self, *, protocolo: str) -> ResultadoDriver:
        xml = (
            f'<ConsultarLoteRpsEnvio xmlns="{self._conf.namespace}">'
            f"<Prestador><InscricaoMunicipal></InscricaoMunicipal></Prestador>"
            f"<Protocolo>{protocolo}</Protocolo></ConsultarLoteRpsEnvio>"
        ).encode(self._conf.encoding, errors="replace")
        return await self._chamar(xml, assinar=False)

    async def consultar_nfse_por_rps(self, *, numero_rps: str) -> ResultadoDriver:
        return ResultadoDriver(
            sucesso=False,
            mensagem=(
                "consultar_nfse_por_rps depende do formato de consulta de cada provedor; "
                "não implementado sem a documentação do provedor"
            ),
            erro_categoria=CategoriaErro.MUNICIPIO,
        )

    async def cancelar_nfse(self, *, numero_nfse: str, motivo: str) -> ResultadoDriver:
        xml = (
            f'<CancelarNfseEnvio xmlns="{self._conf.namespace}">'
            f"<Pedido><InfPedidoCancelamento><IdentificacaoNfse>"
            f"<Numero>{numero_nfse}</Numero>"
            f"</IdentificacaoNfse><CodigoCancelamento>{motivo}</CodigoCancelamento>"
            f"</InfPedidoCancelamento></Pedido></CancelarNfseEnvio>"
        ).encode(self._conf.encoding, errors="replace")
        return await self._chamar(xml, assinar=self._conf.assina_rps)

    async def consultar_nfse_tomadas(self, *, cnpj_tomador: str) -> ResultadoDriver:
        return ResultadoDriver(
            sucesso=False,
            mensagem="consultar_nfse_tomadas exige o leiaute específico do provedor",
            erro_categoria=CategoriaErro.MUNICIPIO,
        )

    async def testar_conectividade(self) -> ResultadoDriver:
        """Consulta de status: a chamada mais barata que prova URL + envelope + TLS."""
        xml = (
            f'<ConsultarSituacaoLoteRpsEnvio xmlns="{self._conf.namespace}">'
            f"<Prestador></Prestador><Protocolo></Protocolo>"
            f"</ConsultarSituacaoLoteRpsEnvio>"
        ).encode(self._conf.encoding, errors="replace")
        return await self._chamar(xml, assinar=False)


def assinador_de(certificado: Any, *, alvo: str = "rps") -> Callable[[bytes], Awaitable[bytes]]:
    """Adapta `assinar_rps` ao contrato `Callable[[bytes], Awaitable[bytes]]` do driver.

    Existe para que o driver não importe assinatura e vice-versa: um só lugar faz a ponte,
    e o teste de integração cobre exatamente essa costura.
    """
    from app.nfse.assinatura_rps import AlvoAssinatura, assinar_rps

    alvo_enum = AlvoAssinatura(alvo)

    async def assinar(xml: bytes) -> bytes:
        return assinar_rps(xml, certificado, alvo=alvo_enum).xml

    return assinar
