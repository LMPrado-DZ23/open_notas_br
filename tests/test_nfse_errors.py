"""Parsing de erro da SEFIN: mensagem estruturada, HTML e formatos inesperados.

A SEFIN responde de tudo: JSON com `erros`, XML com `cStat`, página HTML do IIS, texto solto, lista de
strings. Cada formato precisa virar mensagem **legível** e curta — e o resumo não pode confundir
"servidor fora do ar" com "documento rejeitado", porque a ação do cliente é diferente.
"""

from __future__ import annotations

import json

import pytest
from app.nfse.errors import (
    LIMITE_MENSAGEM,
    ErroSefin,
    MensagemSefin,
    TipoErroFiscal,
    _achatar,
    _resumir,
    _uma_mensagem,
    extrair_alertas,
    extrair_mensagens,
)


class TestResumir:
    def test_colapsa_espacos(self) -> None:
        assert _resumir("  dois   espaços ") == "dois espaços"

    def test_html_vira_rotulo(self) -> None:
        """Página do IIS não é mensagem: resumir para o rótulo evita esconder o código real."""
        assert "HTML" in _resumir("<html><body>erro</body></html>")

    def test_texto_longo_e_truncado_com_marcador(self) -> None:
        resumo = _resumir("x" * (LIMITE_MENSAGEM + 50))

        assert len(resumo) <= LIMITE_MENSAGEM + 1
        assert resumo.endswith("…")


class TestAchatar:
    def test_none_devolve_none(self) -> None:
        assert _achatar(None) is None

    def test_texto_passa_pelo_resumo(self) -> None:
        assert _achatar("  ok ") == "ok"

    def test_numero_vira_string(self) -> None:
        assert _achatar(429) == "429"

    @pytest.mark.parametrize("chave", ["descricao", "mensagem", "message", "detail", "texto"])
    def test_dict_usa_a_chave_conhecida(self, chave: str) -> None:
        assert _achatar({chave: "valor"}) == "valor"

    def test_dict_desconhecido_vira_json(self) -> None:
        resultado = _achatar({"a": 1})

        assert json.loads(resultado) == {"a": 1}

    def test_lista_junta_com_ponto_e_virgula(self) -> None:
        assert _achatar(["um", "dois"]) == "um; dois"

    def test_lista_vazia_devolve_none(self) -> None:
        assert _achatar([]) is None

    def test_objeto_desconhecido_usa_str(self) -> None:
        assert _achatar(object()).startswith("<object object")


class TestUmaMensagem:
    def test_string_vazia_devolve_none(self) -> None:
        assert _uma_mensagem("   ") is None

    def test_dict_com_codigo_e_texto(self) -> None:
        mensagem = _uma_mensagem({"codigo": "E123", "descricao": "falhou"})

        assert mensagem is not None
        assert mensagem.codigo == "E123"
        assert "falhou" in mensagem.texto()

    def test_item_nao_dict_usa_achatar(self) -> None:
        mensagem = _uma_mensagem(42)

        assert mensagem is not None and "42" in mensagem.texto()


class TestExtrairMensagens:
    def test_lista_de_strings(self) -> None:
        mensagens = extrair_mensagens(["um", "dois"])

        assert [m.texto() for m in mensagens] == ["um", "dois"]

    def test_string_solta(self) -> None:
        assert extrair_mensagens("  falhou ") != []

    def test_payload_que_nao_e_dict_nem_lista(self) -> None:
        assert extrair_mensagens(99) != []

    @pytest.mark.parametrize("chave", ["erros", "erro", "errors", "mensagens", "message"])
    def test_dict_com_chave_de_erro(self, chave: str) -> None:
        assert extrair_mensagens({chave: [{"descricao": "x"}]}) != []

    def test_dict_com_valor_escalar_na_chave(self) -> None:
        assert extrair_mensagens({"erro": "falhou"}) != []

    def test_dict_sem_chave_conhecida_devolve_vazio(self) -> None:
        assert extrair_mensagens({"outra": 1}) == []


class TestExtrairAlertas:
    def test_payload_nao_dict_devolve_vazio(self) -> None:
        assert extrair_alertas(["x"]) == []

    def test_lista_de_alertas(self) -> None:
        assert extrair_alertas({"alertas": ["atenção"]}) != []

    def test_dict_de_alerta(self) -> None:
        assert extrair_alertas({"avisos": {"descricao": "atenção"}}) != []

    def test_sem_alerta_devolve_vazio(self) -> None:
        assert extrair_alertas({"alertas": 3}) == []


class TestErroSefin:
    def test_transitorio_por_tipo(self) -> None:
        indisponivel = ErroSefin(TipoErroFiscal.INDISPONIVEL, "fora")
        rejeicao = ErroSefin(TipoErroFiscal.REJEICAO, "recusada")

        assert indisponivel.transitorio is True
        assert rejeicao.transitorio is False

    def test_ambiguo_indica_que_pode_ter_sido_processada(self) -> None:
        assert ErroSefin(TipoErroFiscal.AMBIGUO, "timeout").pode_ter_sido_processada is True

    def test_str_inclui_as_mensagens(self) -> None:
        erro = ErroSefin(
            TipoErroFiscal.REJEICAO,
            "recusada",
            [MensagemSefin("E1", "primeira")],
        )

        assert "recusada" in str(erro) and "primeira" in str(erro)
