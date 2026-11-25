"""Testes do contrato NFS-e Nacional: constantes, erros, transporte e adapter.

Nenhum teste aqui toca a rede. O cliente HTTP é exercitado com
`httpx.MockTransport`, que devolve a resposta que o teste define — inclusive
respostas de erro, timeout e falha de TLS. Isso testa o **contrato** (URL, corpo,
campos, classificação de erro), não disponibilidade do serviço.
"""

from __future__ import annotations

from datetime import datetime

import httpx
import pytest
from app.db.models.enums import AmbienteFiscal
from app.nfse.adapter import (
    LoteDistribuicao,
    SefinAdapter,
    SefinMockAdapter,
    SefinNacionalClient,
)
from app.nfse.constants import (
    ADN_HOMOLOGACAO,
    ADN_PRODUCAO,
    INICIO_NT009_PRODUCAO,
    LEIAUTE_ANTERIOR,
    LEIAUTE_NT009,
    SEFIN_HOMOLOGACAO,
    SEFIN_PRODUCAO,
    host_permitido,
    leiaute,
    tp_amb,
)
from app.nfse.errors import (
    AVISO_HOMOLOGACAO,
    ErroSefin,
    MensagemSefin,
    TipoErroFiscal,
    extrair_alertas,
    extrair_mensagens,
)
from app.nfse.transport import gzip_b64, ungzip_b64

DPS_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">'
    b'<infDPS Id="DPS35503081112223330001810000100000000000000001">'
    b"<tpAmb>2</tpAmb></infDPS></DPS>"
)
NFSE_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">'
    b'<infNFSe Id="NFSeMOCK"><chNFSe>355030</chNFSe></infNFSe></NFSe>'
)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
class TestConstantes:
    def test_urls_por_ambiente(self) -> None:
        assert SEFIN_PRODUCAO == "https://sefin.nfse.gov.br/SefinNacional"
        assert "producaorestrita" in SEFIN_HOMOLOGACAO
        assert ADN_PRODUCAO == "https://adn.nfse.gov.br"
        assert "producaorestrita" in ADN_HOMOLOGACAO

    def test_tp_amb(self) -> None:
        assert tp_amb(AmbienteFiscal.PRODUCAO) == "1"
        assert tp_amb(AmbienteFiscal.HOMOLOGACAO) == "2"

    @pytest.mark.parametrize(
        ("url", "esperado"),
        [
            ("https://sefin.nfse.gov.br/SefinNacional/nfse", True),
            ("https://adn.producaorestrita.nfse.gov.br/contribuintes/DFe/0", True),
            ("https://evil.example.com/nfse", False),
            ("https://nfse.gov.br.evil.com/nfse", False),
            ("http://127.0.0.1:8080/nfse", False),
        ],
    )
    def test_allowlist_de_host(self, url: str, esperado: bool) -> None:
        assert host_permitido(url) is esperado

    def test_allowlist_aceita_override_explicito(self) -> None:
        assert host_permitido("http://127.0.0.1:9999/nfse", permitir_override=True) is True


class TestJanelaDeLeiaute:
    def test_homologacao_ja_esta_na_nt009(self) -> None:
        antes = datetime(2026, 1, 1, tzinfo=INICIO_NT009_PRODUCAO.tzinfo)
        assert leiaute(AmbienteFiscal.HOMOLOGACAO, antes) == LEIAUTE_NT009

    def test_producao_antes_de_012_dezembro_usa_leiaute_anterior(self) -> None:
        quando = datetime(2026, 11, 25, tzinfo=INICIO_NT009_PRODUCAO.tzinfo)
        assert leiaute(AmbienteFiscal.PRODUCAO, quando) == LEIAUTE_ANTERIOR

    def test_producao_a_partir_de_012_dezembro_usa_nt009(self) -> None:
        assert leiaute(AmbienteFiscal.PRODUCAO, INICIO_NT009_PRODUCAO) == LEIAUTE_NT009

    def test_producao_depois_da_virada(self) -> None:
        quando = datetime(2027, 1, 1, tzinfo=INICIO_NT009_PRODUCAO.tzinfo)
        assert leiaute(AmbienteFiscal.PRODUCAO, quando) == LEIAUTE_NT009


# ---------------------------------------------------------------------------
# Transporte: gzip + base64
# ---------------------------------------------------------------------------
class TestCompressao:
    def test_ida_e_volta(self) -> None:
        assert ungzip_b64(gzip_b64(DPS_XML)) == DPS_XML

    def test_base64_de_gzip_e_ascii(self) -> None:
        codificado = gzip_b64(DPS_XML)
        assert codificado.isascii()
        assert not codificado.startswith("{")

    def test_conteudo_invalido_vira_erro_de_protocolo(self) -> None:
        with pytest.raises(ErroSefin) as excinfo:
            ungzip_b64("isto-nao-e-base64-gzip")
        assert excinfo.value.tipo is TipoErroFiscal.RESPOSTA_INVALIDA

    def test_deterministico(self) -> None:
        # mtime=0 no gzip: mesmo conteúdo gera o mesmo base64, o que ajuda em teste.
        assert gzip_b64(DPS_XML) == gzip_b64(DPS_XML)


# ---------------------------------------------------------------------------
# Erros
# ---------------------------------------------------------------------------
class TestExtracaoDeErros:
    def test_lista_de_erros(self) -> None:
        payload = {"erros": [{"codigo": "E0312", "descricao": "servico nao cadastrado"}]}
        mensagens = extrair_mensagens(payload)
        assert len(mensagens) == 1
        assert mensagens[0].codigo == "E0312"
        assert "nao cadastrado" in mensagens[0].descricao

    def test_chaves_em_maiuscula(self) -> None:
        payload = {"ERRO": [{"CODIGO": "E0010", "MENSAGEM": "serie invalida"}]}
        mensagens = extrair_mensagens(payload)
        assert mensagens[0].codigo == "E0010"

    def test_erro_unico_como_objeto(self) -> None:
        payload = {"erro": {"codigo": "E1", "mensagem": "falhou"}}
        assert extrair_mensagens(payload)[0].codigo == "E1"

    def test_string_solta(self) -> None:
        assert extrair_mensagens("erro cru")[0].descricao == "erro cru"

    def test_payload_vazio(self) -> None:
        assert extrair_mensagens(None) == []
        assert extrair_mensagens({}) == []

    def test_alertas(self) -> None:
        payload = {"alertas": [{"codigo": "A1", "descricao": "atencao"}]}
        assert extrair_alertas(payload)[0].codigo == "A1"


class TestErroSefin:
    def test_ambiguo_exige_consulta_antes_de_reenviar(self) -> None:
        erro = ErroSefin(TipoErroFiscal.AMBIGUO, "caiu")
        assert erro.pode_ter_sido_processada is True
        assert erro.transitorio is True

    def test_rejeicao_nao_e_transitoria(self) -> None:
        erro = ErroSefin(TipoErroFiscal.REJEICAO, "recusado")
        assert erro.pode_ter_sido_processada is False
        assert erro.transitorio is False

    def test_detecta_duplicidade(self) -> None:
        erro = ErroSefin(
            TipoErroFiscal.REJEICAO,
            "recusado",
            [MensagemSefin("E0001", "já existe NFS-e para esta DPS")],
        )
        assert erro.indica_duplicidade is True

    def test_aviso_de_homologacao_para_codigo_cadastral(self) -> None:
        erro = ErroSefin(
            TipoErroFiscal.REJEICAO,
            "recusado",
            [MensagemSefin("E0312", "servico nao cadastrado")],
            ambiente="2",
        )
        assert erro.as_dict()["aviso_homologacao"] == AVISO_HOMOLOGACAO

    def test_sem_aviso_em_producao(self) -> None:
        erro = ErroSefin(
            TipoErroFiscal.REJEICAO,
            "recusado",
            [MensagemSefin("E0312", "servico nao cadastrado")],
            ambiente="1",
        )
        assert "aviso_homologacao" not in erro.as_dict()


# ---------------------------------------------------------------------------
# Cliente real contra transporte simulado
# ---------------------------------------------------------------------------
def cliente_com(handler, **kwargs) -> SefinNacionalClient:
    ambiente = kwargs.pop("ambiente", AmbienteFiscal.HOMOLOGACAO)
    return SefinNacionalClient(ambiente, transport=httpx.MockTransport(handler), **kwargs)


class TestClienteEmissao:
    def test_emitir_envia_dps_comprimida_e_le_chave(self) -> None:
        capturado: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            capturado["url"] = str(request.url)
            capturado["metodo"] = request.method
            capturado["accept"] = request.headers.get("Accept")
            import json

            corpo = json.loads(request.content)
            capturado["chaves"] = list(corpo)
            capturado["dps"] = ungzip_b64(corpo["dpsXmlGZipB64"])
            return httpx.Response(
                200,
                json={
                    "chaveAcesso": "35503031234567890123456789012345678901234567",
                    "nfseXmlGZipB64": gzip_b64(NFSE_XML),
                    "idDps": "DPS123",
                    "dataHoraProcessamento": "2026-11-25T12:00:00-03:00",
                },
            )

        with cliente_com(handler) as cliente:
            resposta = cliente.emitir(DPS_XML)

        assert capturado["metodo"] == "POST"
        assert capturado["url"] == f"{SEFIN_HOMOLOGACAO}/nfse"
        assert capturado["accept"] == "application/json"
        assert capturado["chaves"] == ["dpsXmlGZipB64"]
        assert capturado["dps"] == DPS_XML
        assert resposta.chave_acesso.startswith("3550303")
        assert resposta.nfse_xml == NFSE_XML
        assert resposta.id_dps == "DPS123"

    def test_rejeicao_preserva_codigo(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400, json={"erros": [{"codigo": "E0312", "descricao": "servico nao cadastrado"}]}
            )

        with cliente_com(handler) as cliente, pytest.raises(ErroSefin) as excinfo:
            cliente.emitir(DPS_XML)

        erro = excinfo.value
        assert erro.tipo is TipoErroFiscal.REJEICAO
        assert erro.codigos == ["E0312"]
        assert erro.http_status == 400

    def test_401_e_autenticacao(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="certificado invalido")

        with cliente_com(handler) as cliente, pytest.raises(ErroSefin) as excinfo:
            cliente.emitir(DPS_XML)

        assert excinfo.value.tipo is TipoErroFiscal.AUTENTICACAO

    def test_503_e_indisponivel(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="fora do ar")

        with cliente_com(handler) as cliente, pytest.raises(ErroSefin) as excinfo:
            cliente.emitir(DPS_XML)

        assert excinfo.value.tipo is TipoErroFiscal.INDISPONIVEL
        assert excinfo.value.transitorio is True

    def test_timeout_de_leitura_na_emissao_e_ambiguo(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("tempo esgotado", request=request)

        with cliente_com(handler) as cliente, pytest.raises(ErroSefin) as excinfo:
            cliente.emitir(DPS_XML)

        assert excinfo.value.tipo is TipoErroFiscal.AMBIGUO
        assert excinfo.value.pode_ter_sido_processada is True

    def test_falha_de_tls_e_autenticacao(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("SSL: certificate verify failed", request=request)

        with cliente_com(handler) as cliente, pytest.raises(ErroSefin) as excinfo:
            cliente.emitir(DPS_XML)

        assert excinfo.value.tipo is TipoErroFiscal.AUTENTICACAO

    def test_resposta_sem_xml_e_protocolo_invalido(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"chaveAcesso": "123"})

        with cliente_com(handler) as cliente, pytest.raises(ErroSefin) as excinfo:
            cliente.emitir(DPS_XML)

        assert excinfo.value.tipo is TipoErroFiscal.RESPOSTA_INVALIDA

    def test_host_nao_oficial_e_recusado_antes_da_rede(self) -> None:
        chamou = {"valor": False}

        def handler(request: httpx.Request) -> httpx.Response:
            chamou["valor"] = True
            return httpx.Response(200, json={})

        cliente = SefinNacionalClient(
            AmbienteFiscal.HOMOLOGACAO,
            base_url="https://servidor-desconhecido.example.com",
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(ErroSefin) as excinfo:
            cliente.emitir(DPS_XML)

        assert excinfo.value.tipo is TipoErroFiscal.VALIDACAO_LOCAL
        assert chamou["valor"] is False, "não pode haver requisição para host não oficial"


class TestClienteConsulta:
    def test_consultar_dps_inexistente_devolve_none(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"erro": "nao encontrada"})

        with cliente_com(handler) as cliente:
            assert cliente.consultar_dps("DPS-inexistente") is None

    def test_consultar_dps_devolve_chave(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url).endswith("/dps/DPS123")
            return httpx.Response(200, json={"chaveAcesso": "355030"})

        with cliente_com(handler) as cliente:
            assert cliente.consultar_dps("DPS123") == "355030"

    def test_consultar_nfse(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"chaveAcesso": "355", "nfseXmlGZipB64": gzip_b64(NFSE_XML)},
            )

        with cliente_com(handler) as cliente:
            resposta = cliente.consultar_nfse("355")
        assert resposta.nfse_xml == NFSE_XML

    def test_evento_envia_pedido_correto(self) -> None:
        capturado: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            corpo = json.loads(request.content)
            capturado["chaves"] = list(corpo)
            capturado["url"] = str(request.url)
            return httpx.Response(200, json={"eventoXmlGZipB64": gzip_b64(b"<evento/>")})

        with cliente_com(handler) as cliente:
            resposta = cliente.registrar_evento("355", b"<pedido/>")

        assert capturado["chaves"] == ["pedidoRegistroEventoXmlGZipB64"]
        assert str(capturado["url"]).endswith("/nfse/355/eventos")
        assert resposta.evento_xml == b"<evento/>"


class TestClienteADN:
    def test_distribuicao_le_lote_e_descomprime_xml(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert "/contribuintes/DFe/0" in str(request.url)
            assert "lote=true" in str(request.url)
            return httpx.Response(
                200,
                json={
                    "StatusProcessamento": "DOCUMENTOS_LOCALIZADOS",
                    "LoteDFe": [
                        {
                            "NSU": 0,
                            "ChaveAcesso": "355030",
                            "TipoDocumento": "NFSE",
                            "ArquivoXml": gzip_b64(NFSE_XML),
                            "DataHoraGeracao": "2026-11-25T12:00:00",
                        }
                    ],
                    "Alertas": [],
                },
            )

        with cliente_com(handler) as cliente:
            lote = cliente.distribuicao_dfe(0)

        assert isinstance(lote, LoteDistribuicao)
        assert lote.status == "DOCUMENTOS_LOCALIZADOS"
        assert lote.documentos[0].nsu == 0
        assert lote.documentos[0].xml == NFSE_XML

    def test_status_404_com_corpo_de_lote_e_lido(self) -> None:
        # O ADN responde 404 com corpo normal: o status do corpo é que vale.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                404, json={"StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO", "LoteDFe": []}
            )

        with cliente_com(handler) as cliente:
            lote = cliente.distribuicao_dfe(10)
        assert lote.status == "NENHUM_DOCUMENTO_LOCALIZADO"
        assert lote.documentos == []

    def test_rejeicao_do_adn(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "StatusProcessamento": "REJEICAO",
                    "Erros": [{"codigo": "E1", "descricao": "consulta recusada"}],
                },
            )

        with cliente_com(handler) as cliente, pytest.raises(ErroSefin) as excinfo:
            cliente.distribuicao_dfe(0)
        assert excinfo.value.tipo is TipoErroFiscal.REJEICAO

    def test_resposta_sem_status_e_invalida(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"algo": "inesperado"})

        with cliente_com(handler) as cliente, pytest.raises(ErroSefin) as excinfo:
            cliente.distribuicao_dfe(0)
        assert excinfo.value.tipo is TipoErroFiscal.RESPOSTA_INVALIDA


# ---------------------------------------------------------------------------
# Dublê offline
# ---------------------------------------------------------------------------
class TestMockAdapter:
    def test_implementa_o_protocolo(self) -> None:
        assert isinstance(SefinMockAdapter(), SefinAdapter)

    def test_cliente_real_implementa_o_protocolo(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            return httpx.Response(200, json={})

        with cliente_com(handler) as cliente:
            assert isinstance(cliente, SefinAdapter)

    def test_fluxo_completo_offline(self) -> None:
        adapter = SefinMockAdapter()

        emissao = adapter.emitir(DPS_XML)
        assert len(emissao.chave_acesso) == 50
        assert adapter.consultar_dps(emissao.id_dps or "") == emissao.chave_acesso

        evento = adapter.registrar_evento(emissao.chave_acesso, b"<pedido/>")
        assert b"evento" in evento.evento_xml
        assert adapter.consultar_evento(emissao.chave_acesso, "CANCELAMENTO") == evento.evento_xml

        lote = adapter.distribuicao_dfe(0)
        assert lote.status == "DOCUMENTOS_LOCALIZADOS"

    def test_emissao_devolve_xml_da_nfse(self) -> None:
        adapter = SefinMockAdapter(xml_nfse=NFSE_XML)
        assert adapter.emitir(DPS_XML).nfse_xml == NFSE_XML

    def test_erro_configuravel(self) -> None:
        erro = ErroSefin(TipoErroFiscal.REJEICAO, "recusado", [MensagemSefin("E1", "x")])
        adapter = SefinMockAdapter(falhar_emissao=erro)
        with pytest.raises(ErroSefin) as excinfo:
            adapter.emitir(DPS_XML)
        assert excinfo.value is erro

    def test_timeout_ambiguo_configuravel(self) -> None:
        adapter = SefinMockAdapter(falhar_timeout=True)
        with pytest.raises(ErroSefin) as excinfo:
            adapter.emitir(DPS_XML)
        assert excinfo.value.pode_ter_sido_processada is True
