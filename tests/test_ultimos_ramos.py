"""Últimos ramos descobertos de `app/`, cada um com uma asserção de comportamento.

A cobertura existente exercita o caminho feliz; aqui estão os contratos que ficaram
de fora: o fallback de encoding do provedor ABRASF, a recusa de rede da consulta de
CNPJ, o teto/mínimo do catálogo de eventos, o fechamento do cliente HTTP próprio do
webhook e a tradução de falha do assinador em erro de validação local.

Nenhum teste toca a rede: todo HTTP é `httpx.MockTransport` ou dublê injetado, e
nenhum certificado real é usado.
"""

from __future__ import annotations

import logging
from datetime import date
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from app.cnpj.client import BrasilApiCnpj, FonteIndisponivel
from app.db import session as db_session
from app.integrations.base import ErroDeIntegracao
from app.integrations.brizu.conector import ConectorBrizu
from app.nfse import adapter as adapter_mod
from app.nfse.adapter import SefinMockAdapter, SefinNacionalClient, _nfse_de_dps
from app.nfse.assinatura_rps import AlvoAssinatura, assinar_rps
from app.nfse.constants import NS_NFSE
from app.nfse.drivers import CategoriaErro
from app.nfse.drivers_abrasf import (
    AbrasfBaseDriver,
    ConfiguracaoAbrasf,
    ErroAbrasf,
    desenvelopar,
    interpretar,
)
from app.nfse.errors import ErroSefin, TipoErroFiscal
from app.nfse.eventos_tipos import ErroDeEventoCatalogo, construir_evento, validar_campo
from app.nfse.signer import ErroAssinatura
from app.nfse.transport import gzip_b64
from app.tenants.schemas import TenantCreate
from app.webhooks import service as webhook_service
from lxml import etree
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# app/nfse/drivers_abrasf.py
# ---------------------------------------------------------------------------
URL_ABRASF = "https://provedor.example/nfse"
NS_ABRASF = "http://www.abrasf.org.br/nfse.xsd"
NS_SOAP12 = "http://www.w3.org/2003/05/soap-envelope"

RPS_ABRASF = f'<EnviarLoteRpsEnvio xmlns="{NS_ABRASF}"><LoteRps/></EnviarLoteRpsEnvio>'.encode()


class _TransporteFalso:
    """Transporte SOAP que devolve resposta fixa e registra os corpos enviados."""

    def __init__(self, resposta: bytes | None = None) -> None:
        self._resposta = resposta or _resposta_soap(
            f'<EnviarLoteRpsResposta xmlns="{NS_ABRASF}"><Protocolo>PROT-9</Protocolo>'
            "</EnviarLoteRpsResposta>"
        )
        self.corpos: list[bytes] = []

    async def enviar(self, *, url: str, corpo: bytes, encoding: str) -> bytes:
        self.corpos.append(corpo)
        return self._resposta


def _resposta_soap(corpo: str) -> bytes:
    return (
        f'<soap:Envelope xmlns:soap="{NS_SOAP12}"><soap:Body>{corpo}</soap:Body></soap:Envelope>'
    ).encode()


def _driver_abrasf(transporte: _TransporteFalso, **extra: Any) -> AbrasfBaseDriver:
    return AbrasfBaseDriver(
        configuracao=ConfiguracaoAbrasf(url=URL_ABRASF, namespace=NS_ABRASF, **extra),
        transporte=transporte,
    )


def _sem_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _buscar_local(xml: bytes, nome: str) -> etree._Element | None:
    """Busca por nome local: o `envelopar` reescreve os filhos com prefixo `nfe:`."""
    raiz = etree.fromstring(xml)
    for elemento in raiz.iter():
        if _sem_namespace(str(elemento.tag)) == nome:
            return elemento
    return None


class TestFallbackDeEncodingAbrasf:
    def test_resposta_latin1_que_declara_utf8_e_reparada(self) -> None:
        # Provedor legado: o cabeçalho diz UTF-8, os bytes são ISO-8859-1. Sem o
        # fallback, o lxml recusa e a nota fica sem resposta legível.
        resposta = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<soap:Envelope xmlns:soap="{NS_SOAP12}"><soap:Body>'
            f'<EnviarLoteRpsResposta xmlns="{NS_ABRASF}"><Protocolo>Serviço</Protocolo>'
            "</EnviarLoteRpsResposta></soap:Body></soap:Envelope>"
        ).encode("iso-8859-1")

        elemento = desenvelopar(resposta, encoding="ISO-8859-1")

        protocolo = elemento.find(".//{*}Protocolo")
        assert protocolo is not None and protocolo.text == "Serviço"

    def test_resposta_binaria_vira_erro_de_abrasf(self) -> None:
        # Ilegível nas duas tentativas: erro do provedor, não exceção crua de parser.
        with pytest.raises(ErroAbrasf, match="resposta não é XML"):
            desenvelopar(b"\x00\x01\x02binario")

    def test_interpretar_traduz_resposta_ilegivel_em_erro_do_municipio(self) -> None:
        resultado = interpretar(b"\x00\x01\x02binario")

        assert resultado.sucesso is False
        assert resultado.erro_categoria is CategoriaErro.MUNICIPIO


class TestOperacoesDoDriverAbrasf:
    async def test_cancelamento_leva_numero_e_motivo_no_pedido(self) -> None:
        transporte = _TransporteFalso()

        resultado = await _driver_abrasf(transporte, assina_rps=False).cancelar_nfse(
            numero_nfse="42", motivo="1"
        )

        assert resultado.sucesso is True
        pedido = transporte.corpos[0]
        assert _buscar_local(pedido, "CancelarNfseEnvio") is not None
        numero = _buscar_local(pedido, "Numero")
        codigo = _buscar_local(pedido, "CodigoCancelamento")
        assert numero is not None and numero.text == "42"
        assert codigo is not None and codigo.text == "1"

    async def test_cancelamento_assina_quando_o_provedor_exige(self) -> None:
        transporte = _TransporteFalso()
        assinados: list[bytes] = []

        async def assinar(xml: bytes) -> bytes:
            assinados.append(xml)
            return xml.replace(b"</CancelarNfseEnvio>", b"<Assinado/></CancelarNfseEnvio>")

        driver = AbrasfBaseDriver(
            configuracao=ConfiguracaoAbrasf(url=URL_ABRASF, namespace=NS_ABRASF, assina_rps=True),
            transporte=transporte,
            assinador=assinar,
        )

        await driver.cancelar_nfse(numero_nfse="7", motivo="2")

        assert assinados and b"CancelarNfseEnvio" in assinados[0]
        assert _buscar_local(transporte.corpos[0], "Assinado") is not None

    async def test_conectividade_consulta_situacao_sem_exigir_assinatura(self) -> None:
        transporte = _TransporteFalso()
        # `assina_rps=True` não pode obrigar assinatura na consulta de situação.
        driver = _driver_abrasf(transporte, assina_rps=True)

        resultado = await driver.testar_conectividade()

        assert resultado.sucesso is True
        assert _buscar_local(transporte.corpos[0], "ConsultarSituacaoLoteRpsEnvio") is not None

    async def test_emissao_assina_o_lote_configurado(self) -> None:
        transporte = _TransporteFalso()
        assinados: list[bytes] = []

        async def assinar(xml: bytes) -> bytes:
            assinados.append(xml)
            return xml

        driver = AbrasfBaseDriver(
            configuracao=ConfiguracaoAbrasf(url=URL_ABRASF, namespace=NS_ABRASF, assina_lote=True),
            transporte=transporte,
            assinador=assinar,
        )

        await driver.emitir_rps(dados={"xml": RPS_ABRASF})

        assert assinados == [RPS_ABRASF]


# ---------------------------------------------------------------------------
# app/nfse/adapter.py
# ---------------------------------------------------------------------------
def _resultado_http(status: int = 200, json: object = None, texto: str = "") -> SimpleNamespace:
    return SimpleNamespace(status_code=status, json=json, texto=texto)


def _cliente_sefin_sem_mtls() -> SefinNacionalClient:
    """Cliente sem `__init__`: o alvo é o mapeamento status → resposta, não o mTLS."""
    from app.db.models.enums import AmbienteFiscal

    cliente = object.__new__(SefinNacionalClient)
    cliente.ambiente = AmbienteFiscal.HOMOLOGACAO
    cliente.base_url = "https://sefin.producaorestrita.nfse.gov.br/SefinNacional"
    cliente.adn_base_url = "https://adn.producaorestrita.nfse.gov.br"
    cliente.permitir_host_nao_oficial = False
    cliente._cliente = None
    return cliente


class TestAdapterNacional:
    def test_timeout_da_parametrizacao_chega_ao_executor(self, monkeypatch) -> None:
        capturado: dict[str, Any] = {}

        def executar_falso(*args: Any, **kwargs: Any) -> SimpleNamespace:
            capturado["args"] = args
            capturado.update(kwargs)
            return _resultado_http(200, {"aliquota": "0.05"})

        monkeypatch.setattr(adapter_mod, "executar", executar_falso)
        cliente = _cliente_sefin_sem_mtls()

        resposta = cliente.aliquota_municipal("5200258", "010701", date(2026, 11, 1))

        assert resposta.encontrado is True
        assert capturado["timeout"] == adapter_mod.TIMEOUT_CONSULTA
        assert capturado["args"][2].endswith(
            "/parametrizacao/5200258/010701.000/2026-11-01/aliquota"
        )

    def test_consultar_evento_devolve_o_xml_descompactado(self) -> None:
        pedido = b"<evento>cancelamento</evento>"
        cliente = _cliente_sefin_sem_mtls()
        chamadas: list[tuple[str, str, str]] = []

        def chamar(metodo: str, url: str, operacao: str, **kwargs: Any) -> SimpleNamespace:
            chamadas.append((metodo, url, operacao))
            return _resultado_http(200, {"eventoXmlGZipB64": gzip_b64(pedido)})

        cliente._chamar = chamar  # type: ignore[method-assign]

        chave = "1" * 50
        assert cliente.consultar_evento(chave, "101101", 2) == pedido
        assert chamadas == [
            ("GET", f"{cliente.base_url}/nfse/{chave}/eventos/101101/2", "consultar_evento")
        ]

    def test_consulta_da_nfse_emitida_devolve_o_registro_guardado(self) -> None:
        adapter = SefinMockAdapter(xml_nfse=b"<NFSe><cStat>100</cStat></NFSe>")
        emissao = adapter.emitir(b"<nao-fechado>")

        assert adapter.consultar_nfse(emissao.chave_acesso) is emissao

    def test_valor_nao_numerico_vira_base_zero_na_nfse_do_duble(self) -> None:
        dps = (
            f'<DPS xmlns="{NS_NFSE}"><infDPS Id="DPS1">'
            "<valores><vServPrest><vServ>abc</vServ></vServPrest></valores>"
            "</infDPS></DPS>"
        ).encode()

        xml = _nfse_de_dps(dps, "1" * 50)

        # O valor original é preservado no documento; só a base de IBS/CBS cai a zero.
        assert b"<vBC>abc</vBC>" in xml
        assert b"<vIBSTot>0.00</vIBSTot>" in xml
        assert b"<vCBS>0.00</vCBS>" in xml


# ---------------------------------------------------------------------------
# app/cnpj/client.py
# ---------------------------------------------------------------------------
CNPJ_VALIDO = "33000167000101"


class TestFontesDeCnpj:
    async def test_falha_de_rede_vira_fonte_indisponivel(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("sem rota ate a fonte", request=request)

        cliente = BrasilApiCnpj(transport=httpx.MockTransport(handler))

        with pytest.raises(FonteIndisponivel, match="falha de rede"):
            await cliente.consultar(CNPJ_VALIDO)

    async def test_status_inesperado_nao_vira_nao_encontrado(self) -> None:
        # 403 é falha da fonte, não "CNPJ não existe": o serviço precisa poder tentar outra.
        transporte = httpx.MockTransport(lambda request: httpx.Response(403, text="forbidden"))
        cliente = BrasilApiCnpj(transport=transporte)

        with pytest.raises(FonteIndisponivel, match="HTTP 403"):
            await cliente.consultar(CNPJ_VALIDO)

    async def test_corpo_que_nao_e_json_vira_indisponivel(self) -> None:
        transporte = httpx.MockTransport(
            lambda request: httpx.Response(200, text="<html>manutencao</html>")
        )
        cliente = BrasilApiCnpj(transport=transporte)

        with pytest.raises(FonteIndisponivel, match="não é JSON"):
            await cliente.consultar(CNPJ_VALIDO)


# ---------------------------------------------------------------------------
# app/nfse/eventos_tipos.py
# ---------------------------------------------------------------------------
CHAVE_EVENTO = "355030" + "11222333000181" + "9" * 30
MOTIVO_EVENTO = "Descricao do evento com mais de quinze caracteres"
DH_EVENTO = "2026-11-25T16:30:00+00:00"


class TestTetoEMinimoDoCatalogoDeEventos:
    def test_campo_em_branco_recusado_antes_do_schema(self) -> None:
        with pytest.raises(ErroDeEventoCatalogo, match="não pode ser vazio"):
            validar_campo("xMotivo", "TSMotivo", "   ")

    def test_motivo_acima_do_teto_recusado(self) -> None:
        with pytest.raises(ErroDeEventoCatalogo, match="no máximo 255"):
            validar_campo("xMotivo", "TSMotivo", "x" * 256)

    def test_cnpj_autor_com_forma_errada_recusado(self) -> None:
        with pytest.raises(ErroDeEventoCatalogo, match="CNPJAutor"):
            construir_evento(
                "101101",
                chave=CHAVE_EVENTO,
                cnpj_autor="123",
                campos={"cMotivo": "1", "xMotivo": MOTIVO_EVENTO},
                dh_evento=DH_EVENTO,
            )


# ---------------------------------------------------------------------------
# app/db/session.py
# ---------------------------------------------------------------------------
class TestPingDoBanco:
    async def test_engine_indisponivel_devolve_false_e_registra(self, monkeypatch, caplog) -> None:
        chamadas: list[bool] = []

        def obter_engine_que_falha():
            chamadas.append(True)
            raise RuntimeError("pool esgotado")

        monkeypatch.setattr(db_session, "obter_engine", obter_engine_que_falha)
        caplog.set_level(logging.WARNING, logger="app.db.session")

        assert await db_session.ping() is False

        assert chamadas == [True]
        assert any(registro.message == "banco_indisponivel" for registro in caplog.records)


# ---------------------------------------------------------------------------
# app/integrations/brizu/conector.py
# ---------------------------------------------------------------------------
class TestConectorBrizu:
    def test_valor_zero_recusado(self) -> None:
        with pytest.raises(ErroDeIntegracao, match="maior que zero"):
            ConectorBrizu().interpretar({"evento_id": "ag-1", "valor": 0, "servico": "Corte"})

    def test_cliente_que_nao_e_objeto_recusado(self) -> None:
        with pytest.raises(ErroDeIntegracao, match="deveria ser objeto"):
            ConectorBrizu().interpretar(
                {
                    "evento_id": "ag-2",
                    "valor": 10,
                    "servico": "Corte",
                    "cliente": "Fulano",
                }
            )


# ---------------------------------------------------------------------------
# app/tenants/schemas.py
# ---------------------------------------------------------------------------
class TestSchemaDeTenant:
    def test_webhook_url_sem_http_recusada(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            TenantCreate(slug="ultimos", nome="Ultimos LTDA", webhook_url="ftp://destino")

        assert "webhook_url" in str(excinfo.value)


# ---------------------------------------------------------------------------
# app/nfse/assinatura_rps.py
# ---------------------------------------------------------------------------
RPS_COM_ID = (
    f'<EnviarLoteRpsEnvio xmlns="{NS_ABRASF}"><Rps>'
    '<InfDeclaracaoPrestacaoServico Id="rps-1"><Competencia>2026-11-01</Competencia>'
    "</InfDeclaracaoPrestacaoServico></Rps></EnviarLoteRpsEnvio>"
).encode()


class TestAssinaturaRps:
    def test_falha_do_assinador_vira_validacao_local(self, monkeypatch) -> None:
        # Erro de assinatura é nosso, não recusa do município: quem lê precisa saber
        # que o problema é local, senão procura no lugar errado.
        def assinar_que_falha(*args: Any, **kwargs: Any) -> None:
            raise ErroAssinatura("chave privada indisponivel")

        monkeypatch.setattr("app.nfse.assinatura_rps.assinar", assinar_que_falha)

        with pytest.raises(ErroSefin) as excinfo:
            assinar_rps(RPS_COM_ID, object(), alvo=AlvoAssinatura.RPS)

        assert excinfo.value.tipo is TipoErroFiscal.VALIDACAO_LOCAL
        assert "falha ao assinar" in str(excinfo.value)


# ---------------------------------------------------------------------------
# app/webhooks/service.py
# ---------------------------------------------------------------------------
class TestEntregaDeWebhook:
    async def test_cliente_http_proprio_e_fechado_apos_a_entrega(
        self, cliente: httpx.AsyncClient, sessao_db, monkeypatch
    ) -> None:
        from app.db.models.enums import StatusWebhook
        from app.db.models.tenant import Tenant
        from sqlalchemy import select

        criado = await cliente.post(
            "/v1/tenants", json={"slug": "ultimos-hook", "nome": "Ultimos Hook LTDA"}
        )
        assert criado.status_code == 201, criado.text
        cabecalho = {"X-API-Key": criado.json()["api_key"]}

        configurado = await cliente.post(
            "/v1/me/webhook",
            json={"url": "https://destino.test/hook"},
            headers=cabecalho,
        )
        assert configurado.status_code == 200, configurado.text

        tenant = (
            await sessao_db.execute(select(Tenant).where(Tenant.slug == "ultimos-hook"))
        ).scalar_one()
        entrega = await webhook_service.enfileirar(
            sessao_db,
            tenant,
            tipo_evento="nfse.autorizada",
            payload={"fatura_id": "f-1"},
            url="https://destino.test/hook",
        )
        assert entrega is not None
        assert entrega.status is StatusWebhook.PENDENTE

        instancias: list[Any] = []

        class _ClienteProprioFalso:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs
                self.fechado = False
                self.entregas: list[dict[str, Any]] = []
                instancias.append(self)

            async def post(
                self, url: str, *, content: bytes, headers: dict[str, str]
            ) -> httpx.Response:
                self.entregas.append({"url": url, "content": content, "headers": headers})
                return httpx.Response(204)

            async def aclose(self) -> None:
                self.fechado = True

        class _HttpxFalso:
            HTTPError = httpx.HTTPError
            AsyncClient = _ClienteProprioFalso

        monkeypatch.setattr(webhook_service, "httpx", _HttpxFalso)

        resultado = await webhook_service.entregar(sessao_db, entrega)

        assert resultado.status is StatusWebhook.ENTREGUE
        assert resultado.codigo_http == 204
        assert len(instancias) == 1
        assert instancias[0].fechado is True, "cliente próprio precisa ser fechado no finally"
        assert instancias[0].kwargs["timeout"] == webhook_service.TIMEOUT_ENTREGA_SEGUNDOS
        assert instancias[0].kwargs["follow_redirects"] is False
        assert instancias[0].entregas[0]["url"] == "https://destino.test/hook"
