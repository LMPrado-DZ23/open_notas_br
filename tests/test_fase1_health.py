"""Testes de healthcheck e metadados.

`/health/live` não toca dependência: prova que o processo responde.
`/health` exige banco e Redis: prova que o serviço pode trabalhar.
"""

from __future__ import annotations

import pytest
from app.core.config import get_settings
from app.core.redis import fechar_redis, ping_redis


class TestLiveness:
    async def test_live_responde_200(self, cliente) -> None:
        resposta = await cliente.get("/health/live")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["status"] == "ok"
        assert corpo["versao"]

    async def test_request_id_no_cabecalho(self, cliente) -> None:
        resposta = await cliente.get("/health/live")
        assert resposta.headers.get("X-Request-ID")

    async def test_request_id_do_cliente_e_preservado(self, cliente) -> None:
        resposta = await cliente.get("/health/live", headers={"X-Request-ID": "abc123"})
        assert resposta.headers["X-Request-ID"] == "abc123"


class TestReadiness:
    async def test_health_200_com_dependencias_de_pe(self, cliente) -> None:
        if not await ping_redis():
            await fechar_redis()
            pytest.skip("Redis indisponível; suba com `docker compose up -d redis`")

        resposta = await cliente.get("/health")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["status"] == "ok"
        assert corpo["verificacoes"]["database"]["ok"] is True
        assert corpo["verificacoes"]["redis"]["ok"] is True
        assert corpo["uptime_segundos"] >= 0
        # O adaptador NFS-e é observável: sem isso, uma instância com dublê ligado é
        # indistinguível de serviço fiscal real (o dublê imita a resposta de propósito).
        assert corpo["nfse_adapter"] == get_settings().nfse_adapter

    async def test_health_503_quando_banco_cai(self, app_teste, cliente) -> None:
        """Simula banco fora para provar que a readiness reprova, não mente."""
        if not await ping_redis():
            await fechar_redis()
            pytest.skip("Redis indisponível")

        import app.api.v1.health as modulo_health

        original = modulo_health.ping

        async def banco_fora() -> bool:
            return False

        modulo_health.ping = banco_fora  # type: ignore[assignment]
        try:
            resposta = await cliente.get("/health")
        finally:
            modulo_health.ping = original  # type: ignore[assignment]

        assert resposta.status_code == 503
        corpo = resposta.json()
        assert corpo["status"] == "degraded"
        assert corpo["verificacoes"]["database"]["ok"] is False


class TestVersao:
    async def test_version(self, cliente) -> None:
        resposta = await cliente.get("/version")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["versao"]
        assert corpo["schema_relatorio"] == "notasbr.relatorio/1"

    async def test_health_sob_v1(self, cliente) -> None:
        resposta = await cliente.get("/v1/health/live")
        assert resposta.status_code == 200
