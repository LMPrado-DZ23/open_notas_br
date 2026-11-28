"""Boot e middleware: request id em falha, aviso de admin sem token e métrica do worker.

Três caminhos que só aparecem em produção:

- exceção **não tratada** precisa sair com `X-Request-ID`, senão o suporte não correlaciona o erro com
  o log;
- produção **sem** `ADMIN_API_TOKEN` responde 503 nas rotas administrativas — o boot precisa avisar em
  vez de descobrir na primeira chamada;
- batimento do worker é gauge 0/1 e **não pode derrubar** `/metrics` quando o Redis cai.
"""

from __future__ import annotations

import base64
import logging

import pytest
from app.main import MiddlewareRequisicao, criar_app
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


class AppComFalha:
    """App mínimo com o middleware e uma rota que estoura."""

    def __init__(self) -> None:
        self.app = FastAPI()
        self.app.add_middleware(MiddlewareRequisicao)

        @self.app.get("/boom")
        async def boom() -> None:
            raise RuntimeError("falha proposital")

        @self.app.get("/ok")
        async def ok() -> dict[str, str]:
            return {"status": "ok"}


class TestRequestId:
    async def test_sucesso_devolve_request_id_do_cliente(self) -> None:
        app = AppComFalha().app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
            resposta = await cliente.get("/ok", headers={"X-Request-ID": "abc123"})

        assert resposta.headers["X-Request-ID"] == "abc123"

    async def test_sucesso_sem_header_gera_request_id(self) -> None:
        app = AppComFalha().app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
            resposta = await cliente.get("/ok")

        assert len(resposta.headers["X-Request-ID"]) == 32

    async def test_excecao_registra_e_propaga(self, caplog) -> None:
        """O middleware não pode engolir a exceção: quem trata é o handler de erro."""
        app = AppComFalha().app

        with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://t"
            ) as cliente:
                await cliente.get("/boom")

        assert "requisicao_falhou" in caplog.text


class TestMetricas:
    async def test_worker_parado_aparece_como_zero(self, monkeypatch) -> None:
        """Redis fora não pode derrubar /metrics: o gauge vira 0 e a série continua."""
        app = criar_app()

        monkeypatch.setattr(
            "app.core.redis.obter_redis",
            lambda: SimpleRedis(erro=ConnectionError("sem redis")),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
            resposta = await cliente.get("/metrics")

        assert resposta.status_code == 200
        assert "opennotas_worker_batimento 0" in resposta.text

    async def test_worker_vivo_aparece_como_um(self, monkeypatch) -> None:
        app = criar_app()
        monkeypatch.setattr(
            "app.core.redis.obter_redis", lambda: SimpleRedis(valor=b"2026-11-28T03:00:00")
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cliente:
            resposta = await cliente.get("/metrics")

        assert "opennotas_worker_batimento 1" in resposta.text


class SimpleRedis:
    def __init__(self, valor: bytes | None = None, erro: Exception | None = None) -> None:
        self._valor = valor
        self._erro = erro

    async def get(self, chave: str):
        if self._erro is not None:
            raise self._erro
        return self._valor


class TestLifespan:
    async def test_producao_sem_admin_token_avisa_e_encerra(self, monkeypatch, caplog) -> None:
        """Produção sem `ADMIN_API_TOKEN` é aviso no boot; o shutdown precisa fechar motor e Redis."""
        from app.core.config import Settings
        from app.main import lifespan

        conf = Settings(
            environment="production",
            nfse_adapter="mock",
            admin_api_token="",
            # A chave-mestra é base64 de 32 bytes (AES-256); string literal precisa decodificar para 32.
            master_encryption_key=base64.b64encode(b"k" * 32).decode(),
        )
        monkeypatch.setattr("app.main.get_settings", lambda: conf)
        monkeypatch.setattr("app.main._verificar_integridade_dos_schemas", lambda s: None)
        monkeypatch.setattr("app.main.configurar_logging", lambda *a, **k: None)

        fechados: list[str] = []

        async def dispose() -> None:
            fechados.append("engine")

        async def fecha_redis() -> None:
            fechados.append("redis")

        monkeypatch.setattr("app.main.dispose_engine", dispose)
        monkeypatch.setattr("app.main.fechar_redis", fecha_redis)

        app = FastAPI()
        with caplog.at_level(logging.WARNING):
            async with lifespan(app):
                pass

        assert "admin_api_token_ausente" in caplog.text
        assert fechados == ["engine", "redis"], "shutdown na ordem: motor, depois redis"
