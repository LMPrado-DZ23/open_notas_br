"""O rate limit está **instalado no app real**? (§58)

Os testes antigos construíam uma `FastAPI()` própria e adicionavam o middleware — provavam que o
middleware funciona, nunca que ele está no fluxo. E não estava: `MiddlewareRateLimit` existia e
`criar_app()` não o registrava, então `RATE_LIMIT_HABILITADO=true` não protegia nada.

Estes testes olham o app de verdade.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.config import Settings
from httpx import ASGITransport, AsyncClient


def _app_com(monkeypatch, **overrides):
    """Cria o app real com a configuração pedida.

    `criar_app()` lê `get_settings()` na construção, então a substituição precisa acontecer antes.
    """
    from app.main import criar_app

    conf = Settings(environment="test", nfse_adapter="mock", **overrides)
    monkeypatch.setattr("app.main.get_settings", lambda: conf)
    return criar_app()


class TestInstalacao:
    def test_middleware_esta_no_app_real(self, monkeypatch) -> None:
        app = _app_com(monkeypatch)

        nomes = [m.cls.__name__ for m in app.user_middleware]

        assert "MiddlewareRateLimit" in nomes, (
            "rate limit não registrado: a flag ligaria algo que ninguém executa"
        )

    def test_requisicao_e_por_fora_do_rate_limit(self, monkeypatch) -> None:
        """429 também precisa de `X-Request-ID` e de log — por isso a ordem importa."""
        app = _app_com(monkeypatch)
        nomes = [m.cls.__name__ for m in app.user_middleware]

        # Starlette embrulha `reversed(user_middleware)`, então o **primeiro** da lista é o mais
        # externo. `MiddlewareRequisicao` precisa estar ali: se o rate limit fosse o mais externo,
        # a resposta 429 sairia sem request id, sem log e sem métrica.
        assert nomes.index("MiddlewareRequisicao") < nomes.index("MiddlewareRateLimit")


class TestComportamentoNoAppReal:
    @pytest.fixture
    def app_limitado(self, monkeypatch):
        return _app_com(monkeypatch, rate_limit_habilitado=True, rate_limit_por_minuto=2)

    async def test_terceira_requisicao_vira_429(self, app_limitado) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_limitado), base_url="http://t"
        ) as cliente:
            cabecalho = {"X-API-Key": f"rl-{uuid.uuid4().hex[:16]}"}
            primeira = await cliente.get("/version", headers=cabecalho)
            segunda = await cliente.get("/version", headers=cabecalho)
            terceira = await cliente.get("/version", headers=cabecalho)

        assert primeira.status_code == 200
        assert segunda.status_code == 200
        assert terceira.status_code == 429, "cota de 2 por minuto não foi aplicada"
        assert terceira.headers["retry-after"]
        assert terceira.headers["content-type"].startswith("application/problem+json")
        # O 429 atravessou o middleware de requisição: tem request id.
        assert terceira.headers.get("X-Request-ID")

    async def test_health_nunca_e_barrado(self, app_limitado) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_limitado), base_url="http://t"
        ) as cliente:
            cabecalho = {"X-API-Key": f"rl-{uuid.uuid4().hex[:16]}"}
            for _ in range(5):
                resposta = await cliente.get("/health/live", headers=cabecalho)

        assert resposta.status_code == 200, "/health/live precisa responder sempre"

    async def test_desligado_nao_barra(self, monkeypatch) -> None:
        app = _app_com(monkeypatch, rate_limit_habilitado=False, rate_limit_por_minuto=1)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
            cabecalho = {"X-API-Key": f"rl-{uuid.uuid4().hex[:16]}"}
            for _ in range(4):
                resposta = await cliente.get("/version", headers=cabecalho)

        assert resposta.status_code == 200
