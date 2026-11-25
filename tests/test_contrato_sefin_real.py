"""Contrato da SEFIN/ADN travado com respostas REAIS capturadas.

As fixtures em `tests/fixtures/sefins/` são respostas de verdade, obtidas com
certificado A1 ICP-Brasil real em operações de leitura. Os testes alimentam os
nossos parsers com elas.

Por que isso importa: contrato fiscal escrito de memória envelhece e erra. Aqui, se
a SEFIN mudar a forma da resposta — ou se alguém "melhorar" o parser e quebrar a
compatibilidade — o teste falha antes da produção.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from app.nfse.adapter import SefinNacionalClient
from app.nfse.errors import ErroSefin, extrair_mensagens
from app.nfse.transport import ResultadoHTTP

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "sefins"


def carregar(nome: str) -> dict:
    return json.loads((FIXTURES / nome).read_text(encoding="utf-8"))


def resultado(nome: str, status: int = 404) -> ResultadoHTTP:
    corpo = carregar(nome)
    return ResultadoHTTP(
        status_code=status,
        json=corpo,
        texto=json.dumps(corpo, ensure_ascii=False),
        duracao_ms=42,
    )


class _ClienteStub:
    """Só o que `_lote_adn` usa: o ambiente para montar a mensagem de erro."""

    ambiente_tpamb = "2"


def interpretar(nome: str, status: int = 404) -> object:
    return SefinNacionalClient._lote_adn(
        _ClienteStub(), resultado(nome, status), nome.split(".")[0]
    )


class TestEnvelopeDeErro:
    def test_dps_nao_encontrada(self) -> None:
        corpo = carregar("dps_nao_encontrada.json")
        mensagens = extrair_mensagens(corpo)
        assert len(mensagens) == 1
        assert mensagens[0].codigo == "E2404"
        assert "identificador de DPS" in mensagens[0].descricao

    def test_nfse_nao_encontrada(self) -> None:
        corpo = carregar("nfse_nao_encontrada.json")
        mensagens = extrair_mensagens(corpo)
        assert mensagens[0].codigo == "E2401"
        assert "Chave de acesso não encontrada" in mensagens[0].descricao

    def test_envelope_tem_campos_que_assumimos(self) -> None:
        corpo = carregar("dps_nao_encontrada.json")
        assert {"tipoAmbiente", "dataHoraProcessamento", "erro"} <= set(corpo)
        assert {"codigo", "descricao"} <= set(corpo["erro"])

    def test_tipo_ambiente_difere_entre_endpoints(self) -> None:
        """Observação real: o mesmo ambiente reporta valores diferentes.

        DPS devolve `tipoAmbiente: 0`; NFS-e devolve `tipoAmbiente: 2`. Nada no
        nosso código pode depender desse campo para inferir ambiente.
        """
        dps = carregar("dps_nao_encontrada.json")["tipoAmbiente"]
        nfse = carregar("nfse_nao_encontrada.json")["tipoAmbiente"]
        assert dps != nfse, "se a SEFIN uniformizar, revise esta suposição"


class TestLoteAdn:
    def test_sem_documento_localizado(self) -> None:
        lote = interpretar("adn_eventos_sem_documento.json", 404)
        assert lote.status == "NENHUM_DOCUMENTO_LOCALIZADO"
        assert lote.documentos == []

    def test_404_com_corpo_normal_nao_vira_erro(self) -> None:
        """ADN devolve 404 com envelope válido: 404 não é falha, é ausência."""
        lote = interpretar("adn_eventos_sem_documento.json", 404)
        assert lote.status == "NENHUM_DOCUMENTO_LOCALIZADO"

    def test_rejeicao_do_dfe_levanta_com_motivo(self) -> None:
        # REJEICAO não é "nenhum documento": é recusa, e o chamador precisa saber.
        with pytest.raises(ErroSefin) as excinfo:
            interpretar("adn_dfe_rejeicao.json", 400)
        erro = excinfo.value
        assert erro.http_status == 400
        # O corpo real vem com Erros vazio; a causa está em TipoConsulta.
        assert "InscricaoCertificado" in str(erro)

    def test_resposta_sem_envelope_levanta(self) -> None:
        corpo = carregar("sefin_eventos_405.json")
        resposta = ResultadoHTTP(status_code=405, json=corpo, texto=json.dumps(corpo), duracao_ms=5)
        with pytest.raises(ErroSefin) as excinfo:
            SefinNacionalClient._lote_adn(_ClienteStub(), resposta, "adn_eventos")
        assert excinfo.value.http_status == 405

    def test_status_desconhecido_e_respeitado(self) -> None:
        corpo = {"StatusProcessamento": "PROCESSANDO", "LoteDFe": []}
        resposta = ResultadoHTTP(status_code=200, json=corpo, texto=json.dumps(corpo), duracao_ms=1)
        lote = SefinNacionalClient._lote_adn(_ClienteStub(), resposta, "adn_dfe")
        assert lote.status == "PROCESSANDO"


class TestRotaDeEventosDaSefin:
    def test_get_nao_e_suportado(self) -> None:
        """A premissa do briefing (`GET /nfse/{chave}/eventos`) está ERRADA.

        A SEFIN respondeu 405 para GET nesse caminho. Nossa implementação usa o
        ADN (`/contribuintes/NFSe/{chave}/Eventos`), que funciona. Este teste
        registra o achado para ninguém "consertar" o código de volta para a rota
        errada.
        """
        corpo = carregar("sefin_eventos_405.json")
        assert "does not support http method" in corpo["message"]
