"""Cliente Redis compartilhado: recriação por event loop e falha aberta no `ping`.

O cliente carrega conexões amarradas ao loop que as abriu. Reutilizá-lo em outro loop dá
`Event loop is closed` na primeira operação — e o sintoma aparece como "Redis indisponível", que é
diagnóstico errado. Aqui o teste fixa a recriação e o fechamento.
"""

from __future__ import annotations

import asyncio

import pytest
from app.core import redis as modulo


class RedisFalso:
    def __init__(self, resposta=True, erro: Exception | None = None) -> None:
        self._resposta = resposta
        self._erro = erro
        self.fechado = 0

    async def ping(self):
        if self._erro is not None:
            raise self._erro
        return self._resposta

    async def aclose(self) -> None:
        self.fechado += 1


@pytest.fixture(autouse=True)
def _limpar_estado():
    modulo._redis = None
    modulo._loop = None
    yield
    modulo._redis = None
    modulo._loop = None


class TestObterRedis:
    async def test_cria_cliente_no_loop_atual(self) -> None:
        cliente = modulo.obter_redis()

        assert cliente is not None
        assert modulo._loop is asyncio.get_running_loop()

    async def test_reutiliza_no_mesmo_loop(self) -> None:
        primeiro = modulo.obter_redis()
        segundo = modulo.obter_redis()

        assert primeiro is segundo

    async def test_recria_quando_o_loop_muda(self) -> None:
        """O ponto do módulo: cliente preso a loop antigo não pode ser reutilizado."""
        primeiro = modulo.obter_redis()
        modulo._loop = None  # simula outro loop

        segundo = modulo.obter_redis()

        assert segundo is not primeiro


class TestPing:
    async def test_verdadeiro_quando_responde(self, monkeypatch) -> None:
        monkeypatch.setattr(modulo, "obter_redis", lambda: RedisFalso(resposta=True))

        assert await modulo.ping_redis() is True

    async def test_falso_quando_falha_sem_explodir(self, monkeypatch, caplog) -> None:
        monkeypatch.setattr(
            modulo, "obter_redis", lambda: RedisFalso(erro=ConnectionError("sem redis"))
        )

        assert await modulo.ping_redis() is False
        assert "redis_indisponivel" in caplog.text


class TestFechar:
    async def test_fecha_e_limpa_o_estado(self, monkeypatch) -> None:
        falso = RedisFalso()
        modulo._redis = falso
        modulo._loop = asyncio.get_running_loop()

        await modulo.fechar_redis()

        assert falso.fechado == 1
        assert modulo._redis is None
        assert modulo._loop is None

    async def test_sem_cliente_e_noop(self) -> None:
        await modulo.fechar_redis()

        assert modulo._redis is None
