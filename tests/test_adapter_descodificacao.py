"""Adaptador SEFIN: decodificação de resposta, parametrização de alíquota e dublê.

O `aliquota_municipal` documenta que o caminho do ADN **não existe** (probe de 25/11/2026 deu 404 do
IIS). Os testes fixam o comportamento para cada status: recusa, encontrado, não encontrado e
indeterminado — porque confundir "não encontrado" com "não sei" faz o sistema zerar alíquota em
silêncio.

Nenhuma chamada de rede: `_chamar` é substituído.
"""

from __future__ import annotations

import base64
import gzip
from datetime import date
from types import SimpleNamespace

import pytest
from app.db.models.enums import AmbienteFiscal
from app.nfse.adapter import (
    SefinMockAdapter,
    SefinNacionalClient,
    _decodificar_xml,
    _get,
)
from app.nfse.errors import ErroSefin, TipoErroFiscal


def _resultado(status: int = 200, json: object = None, texto: str = "") -> SimpleNamespace:
    return SimpleNamespace(status_code=status, json=json, texto=texto)


def _cliente(*, chamar=None) -> SefinNacionalClient:
    """Instância sem `__init__`: o alvo é a lógica, não a montagem do cliente mTLS."""
    cliente = object.__new__(SefinNacionalClient)
    cliente.ambiente = AmbienteFiscal.HOMOLOGACAO
    cliente.base_url = "https://sefin.producaorestrita.nfse.gov.br/SefinNacional"
    cliente.adn_base_url = "https://adn.producaorestrita.nfse.gov.br"
    cliente.permitir_host_nao_oficial = False
    cliente._cliente = None
    cliente._chamar = chamar or (lambda *a, **k: _resultado())
    return cliente


class TestGet:
    def test_nao_dict_devolve_none(self) -> None:
        assert _get([1, 2], "x") is None

    def test_busca_ignorando_caixa(self) -> None:
        assert _get({"ChaveAcesso": "1"}, "chaveacesso") == "1"

    def test_ausente_devolve_none(self) -> None:
        assert _get({"a": 1}, "b") is None


class TestDecodificarXml:
    def test_vazio_devolve_none(self) -> None:
        assert _decodificar_xml("") is None

    def test_nao_string_devolve_none(self) -> None:
        assert _decodificar_xml(b"abc") is None

    def test_gzip_base64_decodifica(self) -> None:
        original = b"<xml/>"

        valor = base64.b64encode(gzip.compress(original)).decode()

        assert _decodificar_xml(valor) == original

    def test_conteudo_que_nao_e_gzip_vira_texto(self) -> None:
        """O ADN às vezes devolve XML puro no campo comprimido; não pode explodir."""
        assert _decodificar_xml("nao-e-gzip") == b"nao-e-gzip"


class TestPropriedades:
    def test_repr_mostra_ambiente_e_url(self) -> None:
        cliente = _cliente()

        assert "homologacao" in repr(cliente)
        assert "producaorestrita" in repr(cliente)

    def test_tpamb_homologacao_e_2(self) -> None:
        assert _cliente().ambiente_tpamb == "2"

    def test_tpamb_producao_e_1(self) -> None:
        cliente = _cliente()
        cliente.ambiente = AmbienteFiscal.PRODUCAO

        assert cliente.ambiente_tpamb == "1"

    def test_leiaute_acompanha_o_ambiente(self) -> None:
        assert _cliente().leiaute_vigente.startswith("v1")


class TestAliquotaMunicipal:
    def test_recusa_401_vira_erro(self) -> None:
        cliente = _cliente(chamar=lambda *a, **k: _resultado(401))

        with pytest.raises(ErroSefin):
            cliente.aliquota_municipal("5200258", "010701", date(2026, 11, 1))

    def test_erro_500_vira_erro(self) -> None:
        cliente = _cliente(chamar=lambda *a, **k: _resultado(503, texto="fora"))

        with pytest.raises(ErroSefin):
            cliente.aliquota_municipal("5200258", "010701", date(2026, 11, 1))

    def test_200_marca_encontrado(self) -> None:
        cliente = _cliente(chamar=lambda *a, **k: _resultado(200, {"aliquota": "0.05"}))

        resposta = cliente.aliquota_municipal("5200258", "010701", date(2026, 11, 1))

        assert resposta.encontrado is True
        assert resposta.aliquota == "0.05"

    def test_200_usa_campo_valor_como_alternativa(self) -> None:
        cliente = _cliente(chamar=lambda *a, **k: _resultado(200, {"valor": 5}))

        resposta = cliente.aliquota_municipal("5200258", "010701", date(2026, 11, 1))

        assert resposta.aliquota == "5"

    def test_404_marca_nao_encontrado(self) -> None:
        """O caminho documentado não existe; 404 é ausência, não falha transitória."""
        cliente = _cliente(chamar=lambda *a, **k: _resultado(404))

        resposta = cliente.aliquota_municipal("5200258", "010701", date(2026, 11, 1))

        assert resposta.encontrado is False

    def test_400_marca_indeterminado(self) -> None:
        cliente = _cliente(chamar=lambda *a, **k: _resultado(400, {"mensagens": []}))

        resposta = cliente.aliquota_municipal("5200258", "010701", date(2026, 11, 1))

        assert resposta.encontrado is None

    def test_status_inesperado_marca_indeterminado_com_http(self) -> None:
        cliente = _cliente(chamar=lambda *a, **k: _resultado(418))

        resposta = cliente.aliquota_municipal("5200258", "010701", date(2026, 11, 1))

        assert resposta.encontrado is None
        assert "418" in (resposta.mensagem or "")


class TestMock:
    def test_emitir_pode_falhar_de_proposito(self) -> None:
        erro = ErroSefin(TipoErroFiscal.REJEICAO, "rejeitada")
        mock = SefinMockAdapter(falhar_emissao=erro)

        with pytest.raises(ErroSefin):
            mock.emitir(b"<DPS/>")

        assert mock.chamadas == [("emitir", b"<DPS/>")]

    def test_consultar_nfse_inexistente_recusa(self) -> None:
        mock = SefinMockAdapter()

        with pytest.raises(ErroSefin):
            mock.consultar_nfse("chave-que-nao-existe")

    def test_context_manager_fecha_sem_erro(self) -> None:
        with SefinMockAdapter() as mock:
            assert mock.fechar() is None

    def test_eventos_nfse_sem_evento_devolve_vazio(self) -> None:
        lote = SefinMockAdapter().eventos_nfse("chave")

        assert lote.status == "NENHUM_DOCUMENTO_LOCALIZADO"
        assert lote.documentos == []


class TestOperacoesComChamarDublado:
    """Cada operação só precisa mapear status → resposta ou erro; a rede é do `_chamar`."""

    def test_consultar_dps_404_devolve_none(self) -> None:
        cliente = _cliente(chamar=lambda *a, **k: _resultado(404))

        assert cliente.consultar_dps("DPS1") is None

    def test_consultar_dps_500_levanta(self) -> None:
        cliente = _cliente(chamar=lambda *a, **k: _resultado(500, texto="erro"))

        with pytest.raises(ErroSefin):
            cliente.consultar_dps("DPS1")

    def test_consultar_dps_200_devolve_chave(self) -> None:
        cliente = _cliente(chamar=lambda *a, **k: _resultado(200, {"chaveAcesso": "52"}))

        assert cliente.consultar_dps("DPS1") == "52"

    def test_dps_existe_usa_head(self) -> None:
        chamadas: list[str] = []

        def chamar(metodo, url, operacao, **kwargs):
            chamadas.append(metodo)
            return _resultado(200)

        assert _cliente(chamar=chamar).dps_existe("DPS1") is True
        assert chamadas == ["HEAD"]

    def test_dps_existe_falso_quando_nao_200(self) -> None:
        assert _cliente(chamar=lambda *a, **k: _resultado(404)).dps_existe("DPS1") is False

    def test_consultar_nfse_404_levanta(self) -> None:
        cliente = _cliente(chamar=lambda *a, **k: _resultado(404, texto="nao achei"))

        with pytest.raises(ErroSefin):
            cliente.consultar_nfse("chave")

    def test_registrar_evento_recusa_levanta(self) -> None:
        cliente = _cliente(chamar=lambda *a, **k: _resultado(400, texto="rejeitado"))

        with pytest.raises(ErroSefin):
            cliente.registrar_evento("chave", b"<evento/>")

    def test_consultar_evento_404_devolve_none(self) -> None:
        """A assinatura é `bytes | None`: evento inexistente não é falha de transporte."""
        cliente = _cliente(chamar=lambda *a, **k: _resultado(404))

        assert cliente.consultar_evento("chave", "101101", 1) is None

    def test_consultar_evento_500_levanta(self) -> None:
        cliente = _cliente(chamar=lambda *a, **k: _resultado(500, texto="erro"))

        with pytest.raises(ErroSefin):
            cliente.consultar_evento("chave", "101101", 1)

    def test_distribuicao_dfe_devolve_lote(self) -> None:
        cliente = _cliente(
            chamar=lambda *a, **k: _resultado(
                200, {"StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO", "LoteDFe": []}
            )
        )

        lote = cliente.distribuicao_dfe(0)

        assert lote.status == "NENHUM_DOCUMENTO_LOCALIZADO"
        assert lote.documentos == []


class TestOperacoesRestantes:
    def test_consultar_evento_devolve_none_em_404(self) -> None:
        cliente = _cliente(chamar=lambda *a, **k: _resultado(404))

        assert cliente.consultar_evento("chave", "101101", 1) is None

    def test_consultar_evento_sem_xml_levanta(self) -> None:
        cliente = _cliente(chamar=lambda *a, **k: _resultado(200, {"outro": 1}))

        with pytest.raises(ErroSefin):
            cliente.consultar_evento("chave", "101101", 1)

    def test_distribuicao_dfe_envia_cnpj_consulta(self) -> None:
        visto: dict = {}

        def chamar(metodo, url, operacao, **kwargs):
            visto.update(kwargs)
            return _resultado(
                200, {"StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO", "LoteDFe": []}
            )

        cliente = _cliente(chamar=chamar)

        cliente.distribuicao_dfe(0, cnpj_consulta="11222333000181")

        assert visto["params"]["cnpjConsulta"] == "11222333000181"

    def test_distribuicao_dfe_sem_cnpj_nao_envia_parametro(self) -> None:
        visto: dict = {}

        def chamar(metodo, url, operacao, **kwargs):
            visto.update(kwargs)
            return _resultado(
                200, {"StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO", "LoteDFe": []}
            )

        _cliente(chamar=chamar).distribuicao_dfe(0)

        assert "cnpjConsulta" not in visto["params"]

    def test_eventos_nfse_devolve_lote(self) -> None:
        cliente = _cliente(
            chamar=lambda *a, **k: _resultado(
                200, {"StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO", "LoteDFe": []}
            )
        )

        lote = cliente.eventos_nfse("chave")

        assert lote.documentos == []


class TestIdentificacaoDaDps:
    def test_extrair_id_de_xml_invalido_devolve_none(self) -> None:
        from app.nfse.adapter import _extrair_id_dps

        assert _extrair_id_dps(b"<nao-fechado>") is None

    def test_extrair_id_encontra_infdps(self) -> None:
        from app.nfse.adapter import _extrair_id_dps

        assert _extrair_id_dps(b'<DPS><infDPS Id="DPS1"/></DPS>') == "DPS1"

    def test_extrair_id_aceita_variante_infdps(self) -> None:
        from app.nfse.adapter import _extrair_id_dps

        assert _extrair_id_dps(b'<DPS><infDps Id="DPS2"/></DPS>') == "DPS2"

    def test_extrair_id_sem_infdps_devolve_none(self) -> None:
        from app.nfse.adapter import _extrair_id_dps

        assert _extrair_id_dps(b"<DPS><outro/></DPS>") is None

    def test_nfse_de_dps_com_xml_invalido_nao_explode(self) -> None:
        from app.nfse.adapter import _nfse_de_dps

        assert b"</" in _nfse_de_dps(b"<nao-fechado>", "chave")
