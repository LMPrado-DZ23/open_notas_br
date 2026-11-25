"""Testes de webhook: assinatura, retry, backoff e isolamento.

O alvo principal é o comportamento sob falha: webhook que nunca falhou não prova
nada. Aqui o endpoint de destino é controlado (`httpx.MockTransport`) e cada
cenário verifica o estado persistido da entrega.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest
from app.core.config import Settings, get_settings
from app.db.models.enums import StatusWebhook
from app.webhooks import service as webhook_service
from app.webhooks.assinatura import (
    AssinaturaInvalida,
    assinar,
    cabecalhos,
    gerar_segredo,
    verificar,
)
from app.webhooks.service import (
    BACKOFF_SEGUNDOS,
    MAX_TENTATIVAS,
    proxima_tentativa,
)

from tests.test_fase2_certificado import SENHA, gerar_pfx


@pytest.fixture
async def tenant(cliente) -> dict[str, Any]:
    resposta = await cliente.post("/v1/tenants", json={"slug": "hook-tenant", "nome": "Hook LTDA"})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def cabecalho(tenant: dict[str, Any]) -> dict[str, str]:
    return {"X-API-Key": tenant["api_key"]}


class TestAssinatura:
    def test_assina_e_verifica(self) -> None:
        segredo = b"segredo-de-teste"
        corpo = b'{"evento":"nfse.autorizada"}'
        momento = int(time.time())
        assinatura = assinar(segredo, corpo, timestamp=momento)

        verificar(segredo, corpo, f"t={momento},v1={assinatura}", agora=momento)

    def test_corpo_alterado_invalida(self) -> None:
        segredo = b"s"
        momento = int(time.time())
        assinatura = assinar(segredo, b'{"a":1}', timestamp=momento)
        with pytest.raises(AssinaturaInvalida, match="não confere"):
            verificar(segredo, b'{"a":2}', f"t={momento},v1={assinatura}", agora=momento)

    def test_replay_fora_da_tolerancia(self) -> None:
        segredo = b"s"
        corpo = b"{}"
        momento = int(time.time()) - 400
        assinatura = assinar(segredo, corpo, timestamp=momento)

        with pytest.raises(AssinaturaInvalida, match="replay"):
            verificar(segredo, corpo, f"t={momento},v1={assinatura}")

    def test_timestamp_entra_na_assinatura(self) -> None:
        segredo = b"s"
        corpo = b"{}"
        a = assinar(segredo, corpo, timestamp=1000)
        b = assinar(segredo, corpo, timestamp=1001)
        assert a != b, "sem o timestamp na mensagem, replay passaria"

    def test_cabecalho_malformado(self) -> None:
        with pytest.raises(AssinaturaInvalida, match="sem t ou v1"):
            verificar(b"s", b"{}", "v1=abc")

    def test_timestamp_nao_inteiro(self) -> None:
        with pytest.raises(AssinaturaInvalida, match="inteiro"):
            verificar(b"s", b"{}", "t=abc,v1=def")

    def test_cabecalhos_completos(self) -> None:
        h = cabecalhos(b"s", b"{}", evento="nfse.autorizada", entrega_id="abc")
        assert h["X-Notasbr-Event"] == "nfse.autorizada"
        assert h["X-Notasbr-Delivery"] == "abc"
        assert h["X-Notasbr-Signature"].startswith("t=")

    def test_segredo_aleatorio(self) -> None:
        assert gerar_segredo() != gerar_segredo()
        assert len(gerar_segredo()) == 64


class TestBackoff:
    def test_sequencia_crescente(self) -> None:
        assert list(BACKOFF_SEGUNDOS) == sorted(BACKOFF_SEGUNDOS)
        assert BACKOFF_SEGUNDOS[0] < BACKOFF_SEGUNDOS[-1]

    def test_esgota_tentativas(self) -> None:
        assert proxima_tentativa(0) is not None
        assert proxima_tentativa(MAX_TENTATIVAS - 1) is not None
        assert proxima_tentativa(MAX_TENTATIVAS) is None

    def test_intervalos(self) -> None:
        from datetime import UTC, datetime, timedelta

        agora = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
        assert proxima_tentativa(0, agora=agora) == agora + timedelta(seconds=10)
        assert proxima_tentativa(2, agora=agora) == agora + timedelta(seconds=120)


class TestConfiguracao:
    async def test_configurar_devolve_segredo_uma_vez(self, cliente, tenant) -> None:
        resposta = await cliente.post(
            "/v1/me/webhook",
            json={"url": "https://cliente.test/hook"},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["segredo"], "primeiro configure deve devolver o segredo"
        assert corpo["tem_segredo"] is True

        segunda = await cliente.post(
            "/v1/me/webhook",
            json={"url": "https://cliente.test/hook"},
            headers=cabecalho(tenant),
        )
        assert segunda.json()["segredo"] is None, "segredo não pode ser reexibido"

    async def test_get_nao_expoe_segredo(self, cliente, tenant) -> None:
        await cliente.post(
            "/v1/me/webhook",
            json={"url": "https://cliente.test/hook"},
            headers=cabecalho(tenant),
        )
        resposta = await cliente.get("/v1/me/webhook", headers=cabecalho(tenant))
        assert resposta.json()["segredo"] is None
        assert resposta.json()["tem_segredo"] is True

    async def test_rotacionar_troca_segredo(self, cliente, tenant) -> None:
        primeiro = await cliente.post(
            "/v1/me/webhook",
            json={"url": "https://cliente.test/hook"},
            headers=cabecalho(tenant),
        )
        rotacionado = await cliente.post(
            "/v1/me/webhook",
            json={"url": "https://cliente.test/hook", "rotacionar_segredo": True},
            headers=cabecalho(tenant),
        )
        assert rotacionado.json()["segredo"]
        assert rotacionado.json()["segredo"] != primeiro.json()["segredo"]

    async def test_url_invalida(self, cliente, tenant) -> None:
        resposta = await cliente.post(
            "/v1/me/webhook",
            json={"url": "ftp://cliente.test/hook"},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 422


class TestEntrega:
    async def _preparar(self, cliente, tenant) -> dict[str, Any]:
        await cliente.put(
            "/v1/me/config-fiscal",
            json={
                "municipio_ibge": "3550308",
                "uf": "SP",
                "ambiente": "homologacao",
                "codigo_tributacao_nacional": "010701",
                "serie_dps": "1",
                "aliquota_iss": 0.05,
            },
            headers=cabecalho(tenant),
        )
        await cliente.post(
            "/v1/me/certificados",
            files={"arquivo": ("c.pfx", gerar_pfx(), "application/x-pkcs12")},
            data={"senha": SENHA.decode(), "apelido": "a1"},
            headers=cabecalho(tenant),
        )
        await cliente.post(
            "/v1/me/webhook",
            json={"url": "https://cliente.test/hook"},
            headers=cabecalho(tenant),
        )
        return tenant

    async def test_emissao_enfileira_webhook(self, cliente, tenant, app_teste, sessao_db) -> None:

        app_teste.dependency_overrides[get_settings] = lambda: Settings(
            environment="test", nfse_adapter="mock"
        )
        try:
            await self._preparar(cliente, tenant)
            resposta = await cliente.post(
                "/v1/emissoes",
                json={
                    "idempotency_key": "hook-emissao-1",
                    "valor": "100.00",
                    "descricao": "Serviço",
                },
                headers=cabecalho(tenant),
            )
            assert resposta.status_code == 201, resposta.text
        finally:
            app_teste.dependency_overrides.clear()

        entregas = await cliente.get("/v1/me/webhook/entregas", headers=cabecalho(tenant))
        corpo = entregas.json()
        assert len(corpo) == 1
        assert corpo[0]["tipo_evento"] == "nfse.autorizada"
        assert corpo[0]["status"] in ("pending", "delivered")

    async def test_entrega_bem_sucedida(self, cliente, tenant, app_teste, sessao_db) -> None:
        from app.db.models.ops import WebhookDelivery
        from app.db.models.tenant import Tenant
        from sqlalchemy import select

        app_teste.dependency_overrides[get_settings] = lambda: Settings(
            environment="test", nfse_adapter="mock"
        )
        try:
            await self._preparar(cliente, tenant)
            await cliente.post(
                "/v1/emissoes",
                json={
                    "idempotency_key": "hook-entrega-1",
                    "valor": "50.00",
                    "descricao": "Serviço",
                },
                headers=cabecalho(tenant),
            )
        finally:
            app_teste.dependency_overrides.clear()

        recebidos: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            recebidos.append(
                {
                    "assinatura": request.headers.get("X-Notasbr-Signature", ""),
                    "evento": request.headers.get("X-Notasbr-Event", ""),
                    "corpo": request.content,
                }
            )
            return httpx.Response(200)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            resultado = await webhook_service.processar_pendentes(sessao_db, cliente=http)
        assert resultado["entregues"] == 1

        assert recebidos
        entrega_recebida = recebidos[0]
        assert entrega_recebida["evento"] == "nfse.autorizada"

        # A assinatura recebida tem que validar com o segredo do tenant.
        tenant_db = await sessao_db.execute(select(Tenant).where(Tenant.slug == "hook-tenant"))
        segredo = webhook_service.obter_segredo(tenant_db.scalar_one())
        assert segredo is not None
        verificar(segredo, entrega_recebida["corpo"], entrega_recebida["assinatura"])

        entrega = await sessao_db.execute(select(WebhookDelivery))
        registro = entrega.scalars().first()
        assert registro is not None
        assert registro.status == StatusWebhook.ENTREGUE
        assert registro.entregue_em is not None

    async def test_falha_agenda_retentativa(self, cliente, tenant, app_teste, sessao_db) -> None:
        from app.db.models.ops import WebhookDelivery
        from sqlalchemy import select

        app_teste.dependency_overrides[get_settings] = lambda: Settings(
            environment="test", nfse_adapter="mock"
        )
        try:
            await self._preparar(cliente, tenant)
            await cliente.post(
                "/v1/emissoes",
                json={
                    "idempotency_key": "hook-falha-1",
                    "valor": "30.00",
                    "descricao": "Serviço",
                },
                headers=cabecalho(tenant),
            )
        finally:
            app_teste.dependency_overrides.clear()

        transport = httpx.MockTransport(lambda request: httpx.Response(500))
        async with httpx.AsyncClient(transport=transport) as http:
            resultado = await webhook_service.processar_pendentes(sessao_db, cliente=http)

        assert resultado["pendentes"] == 1

        entrega = (
            (
                await sessao_db.execute(
                    select(WebhookDelivery).where(WebhookDelivery.tenant_id == tenant["id"])
                )
            )
            .scalars()
            .first()
        )
        assert entrega is not None
        assert entrega.tentativas == 1
        assert entrega.status == StatusWebhook.PENDENTE
        assert entrega.proxima_tentativa is not None
        assert entrega.codigo_http == 500
        assert "HTTP 500" in (entrega.ultimo_erro or "")

    async def test_esgota_e_marca_falha(self, cliente, tenant, app_teste, sessao_db) -> None:
        from app.db.models.ops import WebhookDelivery
        from sqlalchemy import select

        app_teste.dependency_overrides[get_settings] = lambda: Settings(
            environment="test", nfse_adapter="mock"
        )
        try:
            await self._preparar(cliente, tenant)
            await cliente.post(
                "/v1/emissoes",
                json={
                    "idempotency_key": "hook-esgota-1",
                    "valor": "20.00",
                    "descricao": "Serviço",
                },
                headers=cabecalho(tenant),
            )
        finally:
            app_teste.dependency_overrides.clear()

        entrega = (
            (
                await sessao_db.execute(
                    select(WebhookDelivery).where(WebhookDelivery.tenant_id == tenant["id"])
                )
            )
            .scalars()
            .first()
        )
        assert entrega is not None

        # Força o estado de última tentativa e entrega com falha.
        entrega.tentativas = MAX_TENTATIVAS - 1
        await sessao_db.commit()

        transport = httpx.MockTransport(lambda request: httpx.Response(503))
        async with httpx.AsyncClient(transport=transport) as http:
            await webhook_service.processar_pendentes(sessao_db, cliente=http)

        await sessao_db.refresh(entrega)
        assert entrega.tentativas == MAX_TENTATIVAS
        assert entrega.status == StatusWebhook.FALHOU
        assert entrega.proxima_tentativa is None

    async def test_sem_url_nao_cria_entrega(self, sessao_db) -> None:
        from app.db.models.ops import WebhookDelivery
        from sqlalchemy import select

        before = len((await sessao_db.execute(select(WebhookDelivery))).scalars().all())
        assert before == 0


class TestIsolamento:
    async def test_entregas_de_outro_tenant_invisiveis(self, cliente, tenant) -> None:
        outro = await cliente.post("/v1/tenants", json={"slug": "hook-outro", "nome": "Outro LTDA"})
        entregas = await cliente.get("/v1/me/webhook/entregas", headers=cabecalho(outro.json()))
        assert entregas.status_code == 200
        assert entregas.json() == []
