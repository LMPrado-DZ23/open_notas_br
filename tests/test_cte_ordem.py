"""Ordem dos elementos de `ide` extraída do XSD oficial, não de memória."""

from __future__ import annotations

import importlib

modulo = importlib.import_module("scripts.extrair_ordem_cte")


class TestOrdem:
    def test_ide_tem_a_sequencia_oficial(self) -> None:
        itens = modulo.ordem("ide")
        assert len(itens) >= 20, "o schema oficial exige mais campos do que isso"
        # Os primeiros campos são estáveis no leiaute 4.00; se mudarem, o XSD mudou.
        assert itens[0] == "cUF"
        assert itens[1] == "cCT"
        assert itens[2] == "CFOP"
        assert "cMunEnv" in itens, "campo que o validador acusou como faltante"
        assert "modal" in itens

    def test_grupo_inexistente_devolve_vazio(self) -> None:
        assert modulo.ordem("grupoQueNaoExiste") == []

    def test_emit_tem_sequencia(self) -> None:
        itens = modulo.ordem("emit")
        assert itens, "emit é obrigatório no CT-e"
        assert "CNPJ" in itens or "CPF" in itens
