"""Adapter da SEFIN Nacional (emissão, consulta, eventos) e do ADN (distribuição).

Desenho: uma interface (`SefinAdapter`) com duas implementações — o cliente real e
um dublê para teste/desenvolvimento offline. Quem emite nunca importa `httpx`.

Contrato confirmado na implementação de referência (ver `docs/REFERENCIAS.md`):

- emissão: ``POST {sefin}/nfse`` com ``{"dpsXmlGZipB64": ...}`` →
  ``{"chaveAcesso": ..., "nfseXmlGZipB64": ...}``
- consulta de DPS: ``GET {sefin}/dps/{id}`` → 404 quando não existe
- consulta de NFS-e: ``GET {sefin}/nfse/{chave}``
- evento: ``POST {sefin}/nfse/{chave}/eventos`` com
  ``{"pedidoRegistroEventoXmlGZipB64": ...}``
- ADN: ``GET {adn}/contribuintes/DFe/{nsu}?lote=true`` →
  ``{"StatusProcessamento": ..., "LoteDFe": [...]}``

A autenticação é **mTLS com certificado A1**: não há token, header de API key nem
OAuth. Sem certificado válido, o aperto de mão TLS falha e o erro é classificado
como `AUTENTICACAO`, não como indisponibilidade.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol, runtime_checkable

import httpx

from app.certificates.cofre import CertificadoA1
from app.db.models.enums import AmbienteFiscal
from app.nfse.constants import (
    adn_url,
    leiaute,
    sefin_url,
    tp_amb,
)
from app.nfse.errors import (
    ErroSefin,
    MensagemSefin,
    TipoErroFiscal,
    extrair_alertas,
    extrair_mensagens,
)
from app.nfse.transport import (
    TIMEOUT_CONSULTA,
    TIMEOUT_LEITURA,
    ResultadoHTTP,
    criar_cliente,
    erro_http,
    executar,
    gzip_b64,
    ungzip_b64,
)

logger = logging.getLogger(__name__)

#: Namespace do XML de NFS-e (mesmo da DPS).
NS_NFSE_MOCK = "http://www.sped.fazenda.gov.br/nfse"


# ---------------------------------------------------------------------------
# Resultados
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class RespostaEmissao:
    """NFS-e devolvida pela SEFIN (ou pelo dublê)."""

    chave_acesso: str
    nfse_xml: bytes
    id_dps: str | None = None
    alertas: list[MensagemSefin] = field(default_factory=list)
    data_processamento: str | None = None
    bruto: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RespostaEvento:
    """Evento registrado (ex.: cancelamento)."""

    evento_xml: bytes
    data_processamento: str | None = None


@dataclass(slots=True)
class DocumentoDistribuido:
    """Item de `LoteDFe` do ADN."""

    nsu: int | None
    chave_acesso: str | None
    tipo_documento: str
    tipo_evento: str | None
    xml: bytes | None
    data_geracao: str | None = None


@dataclass(slots=True)
class LoteDistribuicao:
    """Resposta de distribuição do ADN.

    `status` é `DOCUMENTOS_LOCALIZADOS`, `NENHUM_DOCUMENTO_LOCALIZADO` ou
    `REJEICAO`. O HTTP status não decide: o corpo decide.
    """

    status: str
    documentos: list[DocumentoDistribuido] = field(default_factory=list)
    alertas: list[MensagemSefin] = field(default_factory=list)


@dataclass(slots=True)
class AliquotaMunicipal:
    """Alíquota cadastrada pelo município no Sistema Nacional."""

    encontrado: bool | None
    aliquota: str | None = None
    mensagem: str | None = None


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
@runtime_checkable
class SefinAdapter(Protocol):
    """O que o motor de emissão precisa do mundo externo."""

    ambiente: AmbienteFiscal

    def emitir(self, dps_assinada: bytes) -> RespostaEmissao: ...

    def consultar_dps(self, id_dps: str) -> str | None: ...

    def consultar_nfse(self, chave: str) -> RespostaEmissao: ...

    def registrar_evento(
        self, chave: str, pedido_assinado: bytes, *, operacao: str = "o evento"
    ) -> RespostaEvento: ...

    def consultar_evento(self, chave: str, tipo: str, n_seq: int = 1) -> bytes | None: ...

    def distribuicao_dfe(
        self, nsu: int, *, cnpj_consulta: str | None = None
    ) -> LoteDistribuicao: ...

    def eventos_nfse(self, chave: str) -> LoteDistribuicao: ...

    def fechar(self) -> None: ...


def _get(dados: Any, chave: str) -> Any:
    """Busca campo por nome, ignorando diferença de maiúscula/minúscula."""
    if not isinstance(dados, dict):
        return None
    alvo = chave.lower()
    for nome, valor in dados.items():
        if str(nome).lower() == alvo:
            return valor
    return None


def _decodificar_xml(valor: Any) -> bytes | None:
    """Decodifica `ArquivoXml` do ADN, que vem comprimido em base64."""
    if not valor or not isinstance(valor, str):
        return None
    try:
        return ungzip_b64(valor)
    except ErroSefin:
        return valor.encode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Cliente real
# ---------------------------------------------------------------------------
class SefinNacionalClient:
    """Cliente HTTP da SEFIN Nacional e do ADN, com mTLS."""

    def __init__(
        self,
        ambiente: AmbienteFiscal,
        certificado: CertificadoA1 | None = None,
        *,
        base_url: str | None = None,
        adn_base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout_leitura: float = TIMEOUT_LEITURA,
        permitir_host_nao_oficial: bool = False,
    ) -> None:
        self.ambiente = ambiente
        self.certificado = certificado
        self.base_url = (base_url or sefin_url(ambiente)).rstrip("/")
        self.adn_base_url = (adn_base_url or adn_url(ambiente)).rstrip("/")
        self.permitir_host_nao_oficial = permitir_host_nao_oficial
        self._cliente = criar_cliente(
            certificado, transport=transport, timeout_leitura=timeout_leitura
        )

    # -- ciclo de vida -------------------------------------------------
    def fechar(self) -> None:
        self._cliente.close()

    def __enter__(self) -> SefinNacionalClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.fechar()

    def __repr__(self) -> str:
        return f"<SefinNacionalClient {self.ambiente.value} {self.base_url}>"

    # -- helpers -------------------------------------------------------
    @property
    def ambiente_tpamb(self) -> str:
        return tp_amb(self.ambiente)

    @property
    def leiaute_vigente(self) -> str:
        return leiaute(self.ambiente)

    def _chamar(
        self,
        metodo: str,
        url: str,
        operacao: str,
        *,
        pode_ser_ambigua: bool = False,
        timeout: httpx.Timeout | float | None = None,
        **kwargs: Any,
    ) -> ResultadoHTTP:
        if timeout is not None:
            kwargs["timeout"] = timeout
        return executar(
            self._cliente,
            metodo,
            url,
            operacao=operacao,
            pode_ser_ambigua=pode_ser_ambigua,
            permitir_override=self.permitir_host_nao_oficial,
            **kwargs,
        )

    def _resposta_nfse(self, resultado: ResultadoHTTP, operacao: str) -> RespostaEmissao:
        base64_xml = _get(resultado.json, "nfseXmlGZipB64")
        if not base64_xml:
            raise ErroSefin(
                TipoErroFiscal.RESPOSTA_INVALIDA,
                f"resposta de {operacao} sem o XML da NFS-e",
                corpo=resultado.texto[:2000],
                ambiente=self.ambiente_tpamb,
            )
        bruto = {
            k: v for k, v in (resultado.json or {}).items() if str(k).lower() != "nfsexmlgzipb64"
        }
        return RespostaEmissao(
            chave_acesso=str(_get(resultado.json, "chaveAcesso") or ""),
            nfse_xml=ungzip_b64(base64_xml),
            id_dps=_get(resultado.json, "idDps"),
            alertas=extrair_alertas(resultado.json),
            data_processamento=_get(resultado.json, "dataHoraProcessamento"),
            bruto=bruto,
        )

    # -- operações -----------------------------------------------------
    def emitir(self, dps_assinada: bytes) -> RespostaEmissao:
        """``POST /nfse``: envia a DPS assinada e recebe a NFS-e gerada.

        Timeout aqui é **ambíguo**: a nota pode ter sido gerada. O chamador deve
        consultar `consultar_dps` antes de reenviar.
        """
        url = f"{self.base_url}/nfse"
        resultado = self._chamar(
            "POST",
            url,
            "emitir",
            pode_ser_ambigua=True,
            json={"dpsXmlGZipB64": gzip_b64(dps_assinada)},
        )
        if resultado.status_code not in (200, 201) or not _get(resultado.json, "chaveAcesso"):
            raise erro_http(resultado, "a SEFIN recusou a DPS", ambiente=self.ambiente_tpamb)
        return self._resposta_nfse(resultado, "emitir")

    def consultar_dps(self, id_dps: str) -> str | None:
        """``GET /dps/{id}``: chave de acesso se a DPS já gerou NFS-e, senão ``None``."""
        url = f"{self.base_url}/dps/{id_dps}"
        resultado = self._chamar("GET", url, "consultar_dps")
        if resultado.status_code == 404:
            return None
        if resultado.status_code != 200:
            raise erro_http(resultado, "falha ao consultar a DPS", ambiente=self.ambiente_tpamb)
        return _get(resultado.json, "chaveAcesso")

    def dps_existe(self, id_dps: str) -> bool:
        """``HEAD /dps/{id}``: verificação barata de existência."""
        url = f"{self.base_url}/dps/{id_dps}"
        resultado = self._chamar("HEAD", url, "dps_existe")
        return resultado.status_code == 200

    def consultar_nfse(self, chave: str) -> RespostaEmissao:
        """``GET /nfse/{chave}``: baixa o XML autorizado."""
        url = f"{self.base_url}/nfse/{chave}"
        resultado = self._chamar("GET", url, "consultar_nfse")
        if resultado.status_code != 200:
            raise erro_http(resultado, "falha ao consultar a NFS-e", ambiente=self.ambiente_tpamb)
        return self._resposta_nfse(resultado, "consultar_nfse")

    def registrar_evento(
        self, chave: str, pedido_assinado: bytes, *, operacao: str = "o evento"
    ) -> RespostaEvento:
        """``POST /nfse/{chave}/eventos``: registra pedido de evento."""
        url = f"{self.base_url}/nfse/{chave}/eventos"
        resultado = self._chamar(
            "POST",
            url,
            "evento",
            pode_ser_ambigua=True,
            json={"pedidoRegistroEventoXmlGZipB64": gzip_b64(pedido_assinado)},
        )
        base64_xml = _get(resultado.json, "eventoXmlGZipB64")
        if resultado.status_code not in (200, 201) or not base64_xml:
            raise erro_http(
                resultado,
                f"a SEFIN recusou {operacao}",
                ambiente=self.ambiente_tpamb,
            )
        return RespostaEvento(
            evento_xml=ungzip_b64(base64_xml),
            data_processamento=_get(resultado.json, "dataHoraProcessamento"),
        )

    def consultar_evento(self, chave: str, tipo: str, n_seq: int = 1) -> bytes | None:
        """``GET /nfse/{chave}/eventos/{tipo}/{nSeq}``."""
        url = f"{self.base_url}/nfse/{chave}/eventos/{tipo}/{n_seq}"
        resultado = self._chamar("GET", url, "consultar_evento")
        if resultado.status_code == 404:
            return None
        base64_xml = _get(resultado.json, "eventoXmlGZipB64")
        if resultado.status_code != 200 or not base64_xml:
            raise erro_http(resultado, "falha ao consultar o evento", ambiente=self.ambiente_tpamb)
        return ungzip_b64(base64_xml)

    def distribuicao_dfe(self, nsu: int, *, cnpj_consulta: str | None = None) -> LoteDistribuicao:
        """ADN ``GET /contribuintes/DFe/{nsu}?lote=true``: até 50 documentos."""
        parametros: dict[str, str] = {"lote": "true"}
        if cnpj_consulta:
            parametros["cnpjConsulta"] = cnpj_consulta
        url = f"{self.adn_base_url}/contribuintes/DFe/{nsu}"
        resultado = self._chamar("GET", url, "adn_dfe", params=parametros)
        return self._lote_adn(resultado, "adn_dfe")

    def eventos_nfse(self, chave: str) -> LoteDistribuicao:
        """ADN ``GET /contribuintes/NFSe/{chave}/Eventos``."""
        url = f"{self.adn_base_url}/contribuintes/NFSe/{chave}/Eventos"
        resultado = self._chamar("GET", url, "adn_eventos")
        return self._lote_adn(resultado, "adn_eventos")

    def _lote_adn(self, resultado: ResultadoHTTP, operacao: str) -> LoteDistribuicao:
        """Interpreta `LoteDistribuicaoNSUResponse`.

        O ADN responde 400/404 **com corpo normal**; o que vale é
        `StatusProcessamento`. Sem esse campo, a resposta não é do serviço.
        """
        status = _get(resultado.json, "StatusProcessamento")
        if not isinstance(status, str):
            if resultado.status_code < 400:
                raise ErroSefin(
                    TipoErroFiscal.RESPOSTA_INVALIDA,
                    f"resposta inesperada do ADN (HTTP {resultado.status_code})",
                    corpo=resultado.texto[:2000],
                    ambiente=self.ambiente_tpamb,
                )
            raise erro_http(resultado, "o ADN recusou a consulta", ambiente=self.ambiente_tpamb)

        status_normalizado = status.upper()
        if status_normalizado == "REJEICAO":
            mensagens = extrair_mensagens(_get(resultado.json, "Erros") or [])
            if not mensagens:
                # Caso real observado: o ADN devolve `REJEICAO` com `Erros: []` e a
                # causa vem em `TipoConsulta` (ex.: "InscricaoCertificado" — o NSU
                # consultado não pertence a este certificado). Sem surfacing desse
                # campo, a mensagem vira "recusou sem informar motivo" e o operador
                # não tem por onde começar. Ver docs/REFERENCIAS.md §11.
                tipo_consulta = _get(resultado.json, "TipoConsulta")
                detalhe = (
                    f"; TipoConsulta={tipo_consulta}" if isinstance(tipo_consulta, str) else ""
                )
                mensagens = [
                    MensagemSefin(
                        None,
                        f"o ADN recusou sem detalhar o motivo (HTTP "
                        f"{resultado.status_code}{detalhe}). "
                        "TipoConsulta indica a consulta recusada — "
                        "InscricaoCertificado sugere que o NSU/escopo não pertence "
                        "a este certificado.",
                    )
                ]
            raise ErroSefin(
                TipoErroFiscal.REJEICAO,
                "o ADN recusou a consulta",
                mensagens,
                http_status=resultado.status_code,
                corpo=resultado.texto[:2000],
                ambiente=self.ambiente_tpamb,
            )

        documentos: list[DocumentoDistribuido] = []
        for item in _get(resultado.json, "LoteDFe") or []:
            nsu_bruto = _get(item, "NSU")
            tipo_evento = _get(item, "TipoEvento")
            documentos.append(
                DocumentoDistribuido(
                    nsu=int(nsu_bruto) if nsu_bruto is not None else None,
                    chave_acesso=_get(item, "ChaveAcesso"),
                    tipo_documento=str(_get(item, "TipoDocumento") or "").upper(),
                    tipo_evento=str(tipo_evento).upper() if tipo_evento else None,
                    xml=_decodificar_xml(_get(item, "ArquivoXml")),
                    data_geracao=_get(item, "DataHoraGeracao"),
                )
            )

        return LoteDistribuicao(
            status=status_normalizado,
            documentos=documentos,
            alertas=extrair_mensagens(_get(resultado.json, "Alertas") or []),
        )

    def aliquota_municipal(
        self, c_mun: str, c_trib_nac: str, competencia: date
    ) -> AliquotaMunicipal:
        """ADN ``GET /parametrizacao/{municipio}/{servico}/{competencia}/aliquota``.

        O serviço precisa de **nove dígitos** no formato observado
        (``cTribNac`` de 6 + ``.000``). Sem esse cadastro a SEFIN recusa a DPS com
        E0312, então esta consulta evita uma rejeição previsível.

        **[CONFIRMADO] que este caminho NÃO existe** (probe de 2026-11-25 com
        certificado A1 ICP-Brasil real contra o ADN de homologação): o servidor
        respondeu HTTP 404 com página IIS, ou seja, rota inexistente — não é
        "não encontrado" de domínio.

        Consequência: qualquer chamada aqui devolve 404 e não traz alíquota. A
        consulta de parametrização precisa do caminho correto, que segue
        **[A VALIDAR]** contra o manual do ADN. Enquanto isso, quem precisa da
        alíquota deve informá-la na configuração fiscal do tenant, em vez de
        depender desta consulta.
        """
        url = (
            f"{self.adn_base_url}/parametrizacao/{c_mun}/"
            f"{c_trib_nac}.000/{competencia.isoformat()}/aliquota"
        )
        resultado = self._chamar("GET", url, "parametrizacao", timeout=TIMEOUT_CONSULTA)
        status = resultado.status_code
        if status in (401, 403, 429, 495, 496) or status >= 500:
            raise erro_http(resultado, "o ADN recusou a consulta", ambiente=self.ambiente_tpamb)
        if status == 200:
            aliquota = _get(resultado.json, "aliquota") or _get(resultado.json, "valor")
            return AliquotaMunicipal(encontrado=True, aliquota=str(aliquota) if aliquota else None)
        if status in (400, 404):
            mensagens = extrair_mensagens(resultado.json)
            texto = "; ".join(m.texto() for m in mensagens) or None
            return AliquotaMunicipal(encontrado=False if status == 404 else None, mensagem=texto)
        return AliquotaMunicipal(encontrado=None, mensagem=f"HTTP {status}")


# ---------------------------------------------------------------------------
# Dublê para teste e desenvolvimento offline
# ---------------------------------------------------------------------------
class SefinMockAdapter:
    """Dublê determinístico: emite, consulta e cancela sem tocar a rede.

    Não substitui teste de homologação. Existe para exercitar o fluxo completo
    (inclusive erro) sem certificado, e para a suíte rodar em CI.
    """

    def __init__(
        self,
        ambiente: AmbienteFiscal = AmbienteFiscal.HOMOLOGACAO,
        *,
        xml_nfse: bytes | None = None,
        falhar_emissao: ErroSefin | None = None,
        falhar_timeout: bool = False,
    ) -> None:
        self.ambiente = ambiente
        #: Quando None, a NFS-e é derivada da DPS recebida em `emitir` — um dublê
        #: que devolve XML fixo faz o DANFSe parecer quebrado e esconde erro real
        #: de extração.
        self.xml_nfse = xml_nfse
        self.falhar_emissao = falhar_emissao
        self.falhar_timeout = falhar_timeout
        self.chamadas: list[tuple[str, Any]] = []
        self._emitidas: dict[str, RespostaEmissao] = {}
        self._por_dps: dict[str, str] = {}
        self._eventos: dict[tuple[str, str, int], bytes] = {}

    def fechar(self) -> None:
        return None

    def __enter__(self) -> SefinMockAdapter:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def emitir(self, dps_assinada: bytes) -> RespostaEmissao:
        self.chamadas.append(("emitir", dps_assinada))
        if self.falhar_emissao is not None:
            raise self.falhar_emissao
        if self.falhar_timeout:
            raise ErroSefin(
                TipoErroFiscal.AMBIGUO,
                "a conexão caiu antes da resposta — o documento pode ter sido gerado",
            )

        id_dps = _extrair_id_dps(dps_assinada)
        chave = _chave_simulada(id_dps)
        # Se o XML da NFS-e não foi fixado explicitamente, deriva da DPS recebida:
        # um dublê que devolve XML vazio faz o DANFSe parecer quebrado e esconde
        # erro real de extração.
        xml_nfse = self.xml_nfse or _nfse_de_dps(dps_assinada, chave)
        resposta = RespostaEmissao(
            chave_acesso=chave,
            nfse_xml=xml_nfse,
            id_dps=id_dps,
            data_processamento="2026-11-25T12:00:00-03:00",
        )
        self._emitidas[chave] = resposta
        if id_dps:
            self._por_dps[id_dps] = chave
        return resposta

    def consultar_dps(self, id_dps: str) -> str | None:
        self.chamadas.append(("consultar_dps", id_dps))
        return self._por_dps.get(id_dps)

    def consultar_nfse(self, chave: str) -> RespostaEmissao:
        self.chamadas.append(("consultar_nfse", chave))
        if chave not in self._emitidas:
            raise ErroSefin(
                TipoErroFiscal.REJEICAO,
                "NFS-e não encontrada",
                [MensagemSefin("E0001", "não encontrada")],
            )
        return self._emitidas[chave]

    def registrar_evento(
        self, chave: str, pedido_assinado: bytes, *, operacao: str = "o evento"
    ) -> RespostaEvento:
        # `operacao` existe no Protocol (usada nas mensagens de erro do cliente real).
        # O dublê precisa aceitar o mesmo contrato, senão os testes passam com uma
        # interface e a produção usa outra.
        self.chamadas.append(("registrar_evento", (chave, pedido_assinado)))
        xml = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<evento xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">'
            b"<infEvento><chNFSe>" + chave.encode() + b"</chNFSe></infEvento></evento>"
        )
        self._eventos[(chave, "CANCELAMENTO", 1)] = xml
        return RespostaEvento(evento_xml=xml, data_processamento="2026-11-25T12:01:00-03:00")

    def consultar_evento(self, chave: str, tipo: str, n_seq: int = 1) -> bytes | None:
        self.chamadas.append(("consultar_evento", (chave, tipo, n_seq)))
        return self._eventos.get((chave, tipo.upper(), n_seq))

    def distribuicao_dfe(self, nsu: int, *, cnpj_consulta: str | None = None) -> LoteDistribuicao:
        self.chamadas.append(("distribuicao_dfe", nsu))
        documentos = [
            DocumentoDistribuido(
                nsu=nsu,
                chave_acesso=chave,
                tipo_documento="NFSE",
                tipo_evento=None,
                xml=resposta.nfse_xml,
                data_geracao=resposta.data_processamento,
            )
            for chave, resposta in self._emitidas.items()
        ]
        status = "DOCUMENTOS_LOCALIZADOS" if documentos else "NENHUM_DOCUMENTO_LOCALIZADO"
        return LoteDistribuicao(status=status, documentos=documentos)

    def eventos_nfse(self, chave: str) -> LoteDistribuicao:
        self.chamadas.append(("eventos_nfse", chave))
        documentos = [
            DocumentoDistribuido(
                nsu=1,
                chave_acesso=chave,
                tipo_documento="EVENTO",
                tipo_evento=tipo,
                xml=xml,
                data_geracao=None,
            )
            for (chave_evento, tipo, _seq), xml in self._eventos.items()
            if chave_evento == chave
        ]
        status = "DOCUMENTOS_LOCALIZADOS" if documentos else "NENHUM_DOCUMENTO_LOCALIZADO"
        return LoteDistribuicao(status=status, documentos=documentos)


def _nfse_de_dps(dps: bytes, chave: str) -> bytes:
    """Monta um XML de NFS-e autorizada a partir da DPS recebida.

    Dublê: valores de IBS/CBS são proporcionais fixos (0,10% de IBS e 0,90% de
    CBS), só para o documento ter conteúdo coerente. **Não** é cálculo fiscal.
    """
    from decimal import Decimal

    from notasbr.xml_util import local, parse_seguro, texto

    try:
        raiz_dps = parse_seguro(dps)
    except Exception:
        raiz_dps = None

    def buscar(caminho: list[str]) -> str:
        if raiz_dps is None:
            return ""
        atual = raiz_dps
        for parte in caminho:
            proximo = None
            for filho in atual:
                if local(filho.tag) == parte:
                    proximo = filho
                    break
            if proximo is None:
                return ""
            atual = proximo
        return texto(atual) or ""

    valor = buscar(["infDPS", "valores", "vServPrest", "vServ"]) or "0.00"
    descricao = buscar(["infDPS", "serv", "cServ", "xDescServ"])
    c_trib = buscar(["infDPS", "serv", "cServ", "cTribNac"])
    c_nbs = buscar(["infDPS", "serv", "cServ", "cNBS"])
    municipio = buscar(["infDPS", "cLocEmi"])
    prestador_doc = buscar(["infDPS", "prest", "CNPJ"]) or buscar(["infDPS", "prest", "CPF"])
    prestador_nome = buscar(["infDPS", "prest", "xNome"])
    tomador_doc = buscar(["infDPS", "toma", "CNPJ"]) or buscar(["infDPS", "toma", "CPF"])
    tomador_nome = buscar(["infDPS", "toma", "xNome"])
    competencia = buscar(["infDPS", "dCompet"])
    serie = buscar(["infDPS", "serie"])
    numero_dps = buscar(["infDPS", "nDPS"])
    dh_emi = buscar(["infDPS", "dhEmi"])

    try:
        base = Decimal(valor)
    except Exception:
        base = Decimal("0")
    ibs_total = (base * Decimal("0.001")).quantize(Decimal("0.01"))
    cbs = (base * Decimal("0.009")).quantize(Decimal("0.01"))

    def esc(valor_texto: str) -> str:
        return valor_texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<NFSe xmlns="{NS_NFSE_MOCK}" versao="1.01">'
        f'<infNFSe Id="NFS{chave}">'
        f"<nNFSe>{esc(numero_dps or '1')}</nNFSe>"
        "<cStat>100</cStat>"
        "<dhProc>2026-11-25T13:12:43-03:00</dhProc>"
        "<ambGer>2</ambGer><finNFSe>0</finNFSe>"
        f"<emit><CNPJ>{esc(prestador_doc)}</CNPJ><xNome>{esc(prestador_nome)}</xNome></emit>"
        f"<DPS><infDPS><serie>{esc(serie)}</serie><nDPS>{esc(numero_dps)}</nDPS>"
        f"<dCompet>{esc(competencia)}</dCompet><dhEmi>{esc(dh_emi)}</dhEmi>"
        f"<toma><CNPJ>{esc(tomador_doc)}</CNPJ><xNome>{esc(tomador_nome)}</xNome></toma>"
        f"<serv><locPrest><cLocPrestacao>{esc(municipio)}</cLocPrestacao></locPrest>"
        f"<cServ><cTribNac>{esc(c_trib)}</cTribNac><cNBS>{esc(c_nbs)}</cNBS>"
        f"<xDescServ>{esc(descricao)}</xDescServ></cServ></serv>"
        f"<valores><vServPrest><vServ>{esc(valor)}</vServ></vServPrest>"
        "<trib><tribMun><tribISSQN>1</tribISSQN><tpRetISSQN>1</tpRetISSQN>"
        "<pAliq>0.0500</pAliq></tribMun></trib></valores>"
        "</infDPS></DPS>"
        f"<valores><vLiq>{esc(valor)}</vLiq></valores>"
        "<IBSCBS><valores><trib><gIBSCBS>"
        "<CST>000</CST><cClassTrib>000001</cClassTrib>"
        f"<vBC>{esc(valor)}</vBC><vIBSTot>{ibs_total}</vIBSTot>"
        f"<gIBSUF><pIBSUF>0.0010</pIBSUF><vIBSUF>{ibs_total}</vIBSUF></gIBSUF>"
        "<gIBSMun><pIBSMun>0.0000</pIBSMun><vIBSMun>0.00</vIBSMun></gIBSMun>"
        f"<gCBS><pCBS>0.0090</pCBS><vCBS>{cbs}</vCBS></gCBS>"
        "</gIBSCBS></trib>"
        f"<vTotIBSCBS>{(ibs_total + cbs).quantize(Decimal('0.01'))}</vTotIBSCBS>"
        "</valores></IBSCBS>"
        "</infNFSe></NFSe>"
    ).encode()


def _extrair_id_dps(dps: bytes) -> str | None:
    """Lê o atributo `Id` de `infDPS` sem depender de namespace."""
    from notasbr.erros import XmlInvalido
    from notasbr.xml_util import local, parse_seguro

    try:
        raiz = parse_seguro(dps)
    except XmlInvalido:
        return None
    for elemento in raiz.iter():
        if local(elemento.tag) == "infDPS":
            return elemento.get("Id")
        if local(elemento.tag) == "infDps":
            return elemento.get("Id")
    return None


def _chave_simulada(id_dps: str | None) -> str:
    """Chave de 50 dígitos determinística para o dublê.

    A chave real da NFS-e nacional não é a de 44 dígitos; o dublê gera 50 dígitos
    apenas para ter formato estável em teste. Não é chave válida.
    """
    import hashlib

    base = (id_dps or "sem-id").encode()
    digest = hashlib.sha256(base).hexdigest()
    digitos = "".join(c for c in digest if c.isdigit()).ljust(50, "0")[:50]
    return digitos
