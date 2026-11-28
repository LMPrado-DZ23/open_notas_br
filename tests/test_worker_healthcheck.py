"""Healthcheck do worker e jobs simples, sem Redis real.

`app/worker/healthcheck.py` estava em **0%**: nenhum teste executava o caminho que o Docker usa para
decidir se o worker está saudável. Um `verificar()` quebrado faria o container reiniciar em laço — e a
suíte não veria.
"""

from __future__ import annotations

import logging

from app.worker import healthcheck
from app.worker import main as worker


class RedisFalso:
    def __init__(
        self, valor: str | None = "2026-11-28T00:00:00+00:00", erro: Exception | None = None
    ):
        self._valor = valor
        self._erro = erro
        self.chamadas: list[tuple[str, str, int | None]] = []

    async def get(self, chave: str) -> str | None:
        if self._erro is not None:
            raise self._erro
        return self._valor

    async def set(self, chave: str, valor: str, ex: int | None = None) -> None:
        self.chamadas.append((chave, valor, ex))


def _montar(monkeypatch, redis: RedisFalso) -> None:
    monkeypatch.setattr(healthcheck, "obter_redis", lambda: redis)

    async def fechar() -> None:
        return None

    monkeypatch.setattr(healthcheck, "fechar_redis", fechar)


class TestHealthcheck:
    async def test_batimento_fresco_sai_zero(self, monkeypatch, capsys) -> None:
        _montar(monkeypatch, RedisFalso(valor="2026-11-28T09:00:00+00:00"))

        assert await healthcheck.verificar() == 0
        assert "healthy" in capsys.readouterr().out

    async def test_chave_ausente_sai_um(self, monkeypatch, capsys) -> None:
        _montar(monkeypatch, RedisFalso(valor=None))

        assert await healthcheck.verificar() == 1
        erro = capsys.readouterr().err
        assert "ausente ou expirada" in erro
        assert worker.CHAVE_HEARTBEAT in erro

    async def test_redis_fora_sai_um_sem_explodir(self, monkeypatch, capsys) -> None:
        """Redis caído é motivo de unhealthy, não de traceback: o Docker precisa do código."""
        _montar(monkeypatch, RedisFalso(erro=ConnectionError("sem conexao")))

        assert await healthcheck.verificar() == 1
        assert "redis inacessível" in capsys.readouterr().err

    def test_main_propaga_o_codigo(self, monkeypatch) -> None:
        async def verificar_falso() -> int:
            return 1

        monkeypatch.setattr(healthcheck, "verificar", verificar_falso)

        assert healthcheck.main() == 1


class TestJobsSimples:
    async def test_ping_responde_pong(self, caplog) -> None:
        with caplog.at_level(logging.INFO):
            assert await worker.ping({"job_id": "abc"}) == "pong"

        assert "job_ping" in caplog.text

    async def test_heartbeat_grava_com_ttl(self) -> None:
        redis = RedisFalso()
        await worker.heartbeat({"redis": redis})

        assert len(redis.chamadas) == 1
        chave, valor, ttl = redis.chamadas[0]
        assert chave == worker.CHAVE_HEARTBEAT
        assert valor.endswith("+00:00")
        assert ttl == worker.TTL_HEARTBEAT_SEGUNDOS

    async def test_ao_encerrar_registra(self, caplog) -> None:
        with caplog.at_level(logging.INFO):
            await worker.ao_encerrar({})

        assert "worker_encerrado" in caplog.text

    async def test_ao_iniciar_configura_logging(self, monkeypatch) -> None:
        chamadas: list[tuple[str, bool]] = []

        def configurar_falso(nivel: str, *, json_output: bool = True) -> None:
            chamadas.append((nivel, json_output))

        monkeypatch.setattr(worker, "configurar_logging", configurar_falso)

        await worker.ao_iniciar({})

        assert chamadas and chamadas[0][0] == worker.get_settings().log_level


class TestEntregarWebhooks:
    async def test_processa_e_commita(self, monkeypatch) -> None:
        commits: list[bool] = []
        contagem = {"entregues": 3}

        class Sessao:
            async def commit(self) -> None:
                commits.append(True)

            async def __aenter__(self) -> Sessao:
                return self

            async def __aexit__(self, *args: object) -> None:
                return None

        class Fabrica:
            def __call__(self) -> Sessao:
                return Sessao()

        async def processar_falso(sessao) -> dict[str, int]:
            return contagem

        monkeypatch.setattr(
            "app.db.session.obter_sessionmaker_worker", lambda: Fabrica(), raising=True
        )
        monkeypatch.setattr("app.webhooks.service.processar_pendentes", processar_falso)

        assert await worker.entregar_webhooks({"redis": RedisFalso()}) == contagem
        assert commits == [True]
