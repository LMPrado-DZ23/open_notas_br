"""Webhook: retry só para falha transitória (§86).

Antes: qualquer não-2xx entrava no backoff de 5 tentativas (10 s → 30 min). Um `404` do endpoint do
cliente nunca ia passar, e a entrega só chegava à DLQ depois de ~42 minutos — com 5 chamadas inúteis.

Regra agora: `4xx` (exceto `408` e `429`) e `3xx` são **permanentes** — fecha na hora e vai para a DLQ.
Timeout, erro de rede, `408`, `429` e `5xx` seguem no backoff.
"""

from __future__ import annotations

import pytest
from app.db.models.enums import StatusWebhook
from app.webhooks.service import _recusa_permanente


class TestClassificacao:
    @pytest.mark.parametrize("codigo", [400, 401, 403, 404, 410, 422, 301, 302])
    def test_permanentes(self, codigo: int) -> None:
        assert _recusa_permanente(codigo) is True

    @pytest.mark.parametrize("codigo", [408, 429, 500, 502, 503, 504, 200, 204])
    def test_transitorios_ou_sucesso(self, codigo: int) -> None:
        assert _recusa_permanente(codigo) is False


class TestEntregaComRecusaPermanente:
    async def test_404_vai_para_dlq_na_primeira_tentativa(self, cliente, sessao_db) -> None:
        """Uma tentativa, sem reagendar, e o item aparece na DLQ."""
        from app.db.models.dlq import ItemDLQ
        from app.db.models.tenant import Tenant
        from app.webhooks import service as webhook_service
        from sqlalchemy import select

        criado = await cliente.post("/v1/tenants", json={"slug": "wh-perm", "nome": "Wh Perm"})
        assert criado.status_code == 201, criado.text
        tenant_api = criado.json()
        await cliente.post(
            "/v1/me/webhook",
            json={"url": "https://cliente.test/hook"},
            headers={"X-API-Key": tenant_api["api_key"]},
        )

        tenant = (
            await sessao_db.execute(select(Tenant).where(Tenant.slug == "wh-perm"))
        ).scalar_one()
        entrega = await webhook_service.enfileirar(
            sessao_db, tenant, tipo_evento="teste", payload={"a": 1}
        )
        await sessao_db.commit()

        class _Resposta:
            status_code = 404

        class _Cliente:
            async def post(self, *a, **k):
                return _Resposta()

            async def aclose(self) -> None:
                return None

        entregue = await webhook_service.entregar(sessao_db, entrega, cliente=_Cliente())
        await sessao_db.commit()

        assert entregue.status is StatusWebhook.FALHOU
        assert entregue.proxima_tentativa is None, "recusa permanente não pode reagendar"
        assert "permanente" in (entregue.ultimo_erro or "")

        na_dlq = (
            (
                await sessao_db.execute(
                    select(ItemDLQ).where(ItemDLQ.tenant_id == tenant.id, ItemDLQ.fila == "webhook")
                )
            )
            .scalars()
            .all()
        )
        assert na_dlq, "falha definitiva precisa chegar à DLQ na primeira tentativa"
