"""Rotas de simulação tributária: catálogo e recusas de cálculo.

Simulação não é emissão: não toca a SEFIN nem grava documento. Mas as recusas importam — 422 com a
lista de erros quando a base é inválida, e **404** quando não há alíquota de referência para o ano, com
a instrução de informar as alíquotas explicitamente.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.api.v1 import tax as rota
from app.tax.rtc import TABELA_ALIQUOTAS
from app.tax.schemas import SimulacaoIn
from fastapi import HTTPException


def _simulacao(**overrides) -> SimulacaoIn:
    """Entrada válida mínima; `overrides` usa Decimal, como o schema exige."""
    base = dict(valor_servico=Decimal("100.00"), ano_fato_gerador=2026)
    base.update(overrides)
    return SimulacaoIn(**base)


class TestAliquotas:
    async def test_lista_ordenada_por_ano(self) -> None:
        saida = await rota.listar_aliquotas()

        anos = [int(a.ano) for a in saida]
        assert anos == sorted(anos)
        assert len(saida) == len(TABELA_ALIQUOTAS)

    async def test_ano_sem_referencia_vira_404_com_instrucao(self) -> None:
        with pytest.raises(HTTPException) as erro:
            await rota.aliquota_do_ano(1900)

        assert erro.value.status_code == 404
        assert "explicitamente" in erro.value.detail

    async def test_ano_com_referencia_devolve(self) -> None:
        ano = min(t.ano for t in TABELA_ALIQUOTAS.values())

        saida = await rota.aliquota_do_ano(ano)

        assert int(saida.ano) == ano


class TestSimulacao:
    async def test_simulacao_valida_devolve_valores(self) -> None:
        saida = await rota.simular(_simulacao())

        assert saida.valido is True
        assert Decimal(saida.base_calculo) == Decimal("100.00")

    async def test_base_negativa_vira_422_com_erros(self) -> None:
        """A rota não escolhe o que mostrar: devolve os erros do motor e a base."""
        with pytest.raises(HTTPException) as erro:
            await rota.simular(_simulacao(desconto_incondicional=Decimal("200.00")))

        assert erro.value.status_code == 422
        assert "erros" in erro.value.detail
        assert "base_calculo" in erro.value.detail

    async def test_ano_sem_tabela_vira_422(self) -> None:
        with pytest.raises(HTTPException) as erro:
            await rota.simular(_simulacao(ano_fato_gerador=2100))

        assert erro.value.status_code == 422


class TestClassificacoes:
    async def test_catalogo_sem_filtro_respeita_limite(self) -> None:
        saida = await rota.listar_classificacoes(None, None, 5)

        assert len(saida) <= 5

    async def test_catalogo_com_busca(self) -> None:
        saida = await rota.listar_classificacoes(None, "servi", 5)

        assert isinstance(saida, list)

    async def test_catalogo_com_ano_usa_vigencia(self) -> None:
        saida = await rota.listar_classificacoes(2026, None, 5)

        assert len(saida) <= 5

    async def test_metadados_do_catalogo(self) -> None:
        saida = await rota.catalogo_classificacoes()

        assert saida.total is not None

    async def test_codigo_inexistente_vira_404(self) -> None:
        with pytest.raises(HTTPException) as erro:
            await rota.obter_classificacao("000000", None)

        assert erro.value.status_code == 404

    async def test_codigo_existente_devolve(self) -> None:
        catalogo = await rota.listar_classificacoes(None, None, 1)
        assert catalogo, "catálogo vazio: nada a consultar"

        saida = await rota.obter_classificacao(catalogo[0].codigo, None)

        assert saida.codigo == catalogo[0].codigo
