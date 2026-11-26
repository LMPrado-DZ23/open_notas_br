"""Middleware de rate limit: desligado por padrão, ativo quando ligado."""

from __future__ import annotations

from app.core.config import Settings
from app.core.middleware_ratelimit import MiddlewareRateLimit
from app.core.ratelimit import ArmazenamentoMemoria
from fastapi import FastAPI
from fastapi.testclient import TestClient


def app_com_limite(limite: int = 3, habilitado: bool = True) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        MiddlewareRateLimit,
        settings=Settings(
            environment="test",
            rate_limit_habilitado=habilitado,
            rate_limit_por_minuto=limite,
        ),
        armazenamento=ArmazenamentoMemoria(),
    )

    @app.get("/v1/x")
    async def x() -> dict:
        return {"ok": True}

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


class TestDesligado:
    def test_padrao_nao_limita(self) -> None:
        # Padrão falso: nenhuma rota existente muda de comportamento.
        assert Settings().rate_limit_habilitado is False

    def test_desligado_permite_acima_do_limite(self) -> None:
        cliente = TestClient(app_com_limite(limite=1, habilitado=False))
        for _ in range(5):
            assert cliente.get("/v1/x").status_code == 200


class TestLigado:
    def test_permite_ate_o_limite(self) -> None:
        cliente = TestClient(app_com_limite(limite=3))
        for _ in range(3):
            assert cliente.get("/v1/x").status_code == 200

    def test_bloqueia_com_429(self) -> None:
        cliente = TestClient(app_com_limite(limite=2))
        cliente.get("/v1/x")
        cliente.get("/v1/x")
        resposta = cliente.get("/v1/x")
        assert resposta.status_code == 429
        assert resposta.headers["content-type"].startswith("application/problem+json")

    def test_429_traz_retry_after(self) -> None:
        cliente = TestClient(app_com_limite(limite=1))
        cliente.get("/v1/x")
        resposta = cliente.get("/v1/x")
        assert int(resposta.headers["Retry-After"]) >= 1

    def test_resposta_de_sucesso_traz_os_headers(self) -> None:
        cliente = TestClient(app_com_limite(limite=10))
        resposta = cliente.get("/v1/x")
        assert resposta.headers["X-RateLimit-Limit"] == "10"
        assert "X-RateLimit-Remaining" in resposta.headers


class TestIsencao:
    def test_health_nunca_e_limitado(self) -> None:
        # Health precisa responder mesmo sob ataque, senão o orquestrador mata o pod.
        cliente = TestClient(app_com_limite(limite=1))
        for _ in range(5):
            assert cliente.get("/health").status_code == 200


class TestChave:
    def test_tenants_distintos_nao_compartilham_cota(self) -> None:
        cliente = TestClient(app_com_limite(limite=1))
        assert cliente.get("/v1/x", headers={"X-API-Key": "chave-aaa"}).status_code == 200
        # Outra chave: cota própria.
        assert cliente.get("/v1/x", headers={"X-API-Key": "chave-bbb"}).status_code == 200
        # Primeira chave estourou.
        assert cliente.get("/v1/x", headers={"X-API-Key": "chave-aaa"}).status_code == 429
