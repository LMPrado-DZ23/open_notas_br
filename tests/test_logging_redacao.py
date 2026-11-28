"""Redação de segredos e formato JSON do logging (§cobertura).

O `FormatadorJSON` é a última barreira antes do disco: se um campo sensível passar por engano, ele
precisa sair como `***`. Estes testes cobrem cada ramo do redigidor e a configuração do logger raiz.
"""

from __future__ import annotations

import json
import logging

import pytest
from app.core.logging import (
    CAMPOS_SENSIVEIS,
    FormatadorJSON,
    FormatadorTexto,
    _redigir,
    configurar_logging,
)


def _registro(**extra: object) -> logging.LogRecord:
    registro = logging.LogRecord(
        name="teste",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="oi",
        args=(),
        exc_info=None,
    )
    for chave, valor in extra.items():
        setattr(registro, chave, valor)
    return registro


class TestRedigir:
    @pytest.mark.parametrize("campo", sorted(CAMPOS_SENSIVEIS))
    def test_campo_sensivel_vira_asteriscos(self, campo: str) -> None:
        assert _redigir(campo, "valor-real") == "***"

    def test_campo_sensivel_ignora_caixa(self) -> None:
        assert _redigir("Senha", "x") == "***"

    @pytest.mark.parametrize("valor", [{"a": 1}, ["x"], ("x",), {"x"}])
    def test_estrutura_vira_asteriscos(self, valor: object) -> None:
        """Estrutura pode conter PII em qualquer profundidade; não se tenta adivinhar."""
        assert _redigir("payload", valor) == "***"

    def test_bytes_vira_tamanho(self) -> None:
        assert _redigir("conteudo", b"\x00\x01\x02") == "<3 bytes>"

    def test_valor_comum_passa(self) -> None:
        assert _redigir("tenant", "acme") == "acme"


class TestFormatadorJSON:
    def test_saida_e_uma_linha_json_valida(self) -> None:
        linha = FormatadorJSON().format(_registro(tenant="acme"))

        carga = json.loads(linha)
        assert carga["mensagem"] == "oi"
        assert carga["nivel"] == "INFO"
        assert carga["tenant"] == "acme"
        assert "\n" not in linha

    def test_segredo_nao_aparece(self) -> None:
        linha = FormatadorJSON().format(_registro(senha="nao-pode-vazar"))

        assert "nao-pode-vazar" not in linha
        assert json.loads(linha)["senha"] == "***"

    def test_chaves_reservadas_nao_viram_campo(self) -> None:
        carga = json.loads(FormatadorJSON().format(_registro()))

        for reservada in ("levelname", "msg", "args", "lineno", "exc_info"):
            assert reservada not in carga

    def test_chave_privada_e_ignorada(self) -> None:
        carga = json.loads(FormatadorJSON().format(_registro(_interno="x")))

        assert "_interno" not in carga

    def test_excecao_e_serializada(self) -> None:
        try:
            raise ValueError("falhou de proposito")
        except ValueError:
            registro = _registro()
            import sys

            registro.exc_info = sys.exc_info()
            carga = json.loads(FormatadorJSON().format(registro))

        assert "ValueError" in carga["excecao"]
        assert "falhou de proposito" in carga["excecao"]

    def test_valor_nao_serializavel_usa_str(self) -> None:
        class Estranho:
            def __str__(self) -> str:
                return "texto"

        carga = json.loads(FormatadorJSON().format(_registro(objeto=Estranho())))

        assert carga["objeto"] == "texto"


class TestConfiguracao:
    @pytest.fixture(autouse=True)
    def _restaurar_logger(self):
        """`configurar_logging` mexe no logger raiz; sem restaurar, o resto da suíte herda DEBUG."""
        raiz = logging.getLogger()
        nivel, handlers = raiz.level, list(raiz.handlers)
        niveis = {
            nome: logging.getLogger(nome).level
            for nome in ("uvicorn.access", "sqlalchemy.engine.Engine", "asyncpg")
        }
        yield
        raiz.setLevel(nivel)
        for manipulador in list(raiz.handlers):
            raiz.removeHandler(manipulador)
        for manipulador in handlers:
            raiz.addHandler(manipulador)
        for nome, valor in niveis.items():
            logging.getLogger(nome).setLevel(valor)

    def test_json_e_padrao(self) -> None:
        configurar_logging("INFO")

        raiz = logging.getLogger()
        assert len(raiz.handlers) == 1
        assert isinstance(raiz.handlers[0].formatter, FormatadorJSON)

    def test_texto_quando_pedido(self) -> None:
        configurar_logging("DEBUG", json_output=False)

        raiz = logging.getLogger()
        assert isinstance(raiz.handlers[0].formatter, FormatadorTexto)
        assert raiz.level == logging.DEBUG

    def test_idempotente_nao_duplica_handler(self) -> None:
        configurar_logging("INFO")
        configurar_logging("INFO")

        assert len(logging.getLogger().handlers) == 1

    def test_bibliotecas_ruidosas_ficam_em_info(self) -> None:
        configurar_logging("DEBUG")

        assert logging.getLogger("sqlalchemy.engine.Engine").level == logging.INFO
        assert logging.getLogger("asyncpg").level == logging.INFO
