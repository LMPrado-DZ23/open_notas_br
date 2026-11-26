"""Admin auth mínima (ADR 0001 opção A) e replay de DLQ."""

from __future__ import annotations

import uuid

import pytest
from app.core.config import Settings, get_settings
from app.worker import dlq as dlq_service

CHAVE_ADMIN = "chave-de-admin-para-teste-123456"


async def criar_tenant(sessao, slug: str):
    from app.db.models.tenant import Tenant

    tenant = Tenant(
        slug=slug,
        nome=f"Tenant {slug}",
        api_key_prefix=slug[:8],
        api_key_hash=f"hash-{slug}"[:16].ljust(16, "0"),
    )
    sessao.add(tenant)
    await sessao.flush()
    return tenant


@pytest.fixture
async def sem_admin(app_teste):
    app_teste.dependency_overrides[get_settings] = lambda: Settings(
        environment="test", admin_habilitado=False
    )
    yield
    app_teste.dependency_overrides.clear()


@pytest.fixture
async def com_admin(app_teste):
    app_teste.dependency_overrides[get_settings] = lambda: Settings(
        environment="test", admin_habilitado=True, admin_api_key=CHAVE_ADMIN
    )
    yield
    app_teste.dependency_overrides.clear()


class TestDesabilitado:
    async def test_rota_responde_404_e_nao_403(self, cliente, sem_admin) -> None:
        # 404 não revela que a rota existe; 403 revelaria.
        resposta = await cliente.post(
            f"/v1/admin/dlq/{uuid.uuid4()}/replay?tenant_id={uuid.uuid4()}"
        )
        assert resposta.status_code == 404

    async def test_padrao_e_desabilitado(self) -> None:
        assert Settings().admin_habilitado is False


class TestAutorizacao:
    async def test_sem_chave_da_401(self, cliente, com_admin) -> None:
        resposta = await cliente.post(
            f"/v1/admin/dlq/{uuid.uuid4()}/replay?tenant_id={uuid.uuid4()}"
        )
        assert resposta.status_code == 401

    async def test_chave_errada_da_401(self, cliente, com_admin) -> None:
        resposta = await cliente.post(
            f"/v1/admin/dlq/{uuid.uuid4()}/replay?tenant_id={uuid.uuid4()}",
            headers={"X-Admin-Key": "errada"},
        )
        assert resposta.status_code == 401

    async def test_api_key_de_tenant_nao_serve(self, cliente, com_admin, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "adm-1")
        await sessao_db.commit()
        # X-API-Key não é X-Admin-Key: tenant não pode reprocessar fila morta.
        resposta = await cliente.post(
            f"/v1/admin/dlq/{uuid.uuid4()}/replay?tenant_id={tenant.id}",
            headers={"X-API-Key": "qualquer"},
        )
        assert resposta.status_code == 401


class TestReplay:
    async def test_admin_reprocessa(self, cliente, com_admin, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "adm-2")
        item = await dlq_service.enfileirar(
            sessao_db, tenant_id=tenant.id, fila="emitir_nfse", payload={"x": 1}
        )
        await sessao_db.commit()

        resposta = await cliente.post(
            f"/v1/admin/dlq/{item.id}/replay?tenant_id={tenant.id}",
            headers={"X-Admin-Key": CHAVE_ADMIN},
        )
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["status"] == "reprocessado"
        assert resposta.json()["tentativas"] == 1

    async def test_replay_duplo_da_409(self, cliente, com_admin, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "adm-3")
        item = await dlq_service.enfileirar(sessao_db, tenant_id=tenant.id, fila="f", payload={})
        await sessao_db.commit()
        cabecalho = {"X-Admin-Key": CHAVE_ADMIN}
        url = f"/v1/admin/dlq/{item.id}/replay?tenant_id={tenant.id}"

        assert (await cliente.post(url, headers=cabecalho)).status_code == 200
        # Replay duplo reenviaria a mesma nota: 409, não 200.
        assert (await cliente.post(url, headers=cabecalho)).status_code == 409

    async def test_tenant_errado_nao_encontra_o_item(self, cliente, com_admin, sessao_db) -> None:
        a = await criar_tenant(sessao_db, "adm-4")
        b = await criar_tenant(sessao_db, "adm-5")
        item = await dlq_service.enfileirar(sessao_db, tenant_id=a.id, fila="f", payload={})
        await sessao_db.commit()

        resposta = await cliente.post(
            f"/v1/admin/dlq/{item.id}/replay?tenant_id={b.id}",
            headers={"X-Admin-Key": CHAVE_ADMIN},
        )
        assert resposta.status_code == 409, "tenant errado não reprocessa item de outro"

    async def test_chave_nao_aparece_na_resposta(self, cliente, com_admin, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "adm-6")
        item = await dlq_service.enfileirar(sessao_db, tenant_id=tenant.id, fila="f", payload={})
        await sessao_db.commit()
        resposta = await cliente.post(
            f"/v1/admin/dlq/{item.id}/replay?tenant_id={tenant.id}",
            headers={"X-Admin-Key": CHAVE_ADMIN},
        )
        assert CHAVE_ADMIN not in resposta.text
