"""Expiração e revogação de API key (§73).

Antes disto a chave vivia para sempre e não havia como matá-la sem emitir outra. Para operar
credencial de terceiro (modo hospedado), isso é insuficiente: vazamento exige revogação, e política
de segurança exige prazo.

O que precisa ser provado:

1. chave **expirada** → 401 com motivo distinto de "inválida";
2. chave **revogada** → 401, e a chave antiga não volta a casar;
3. rotação com prazo grava a validade e **limpa a revogação**;
4. revogação é operação de **admin** (X-Admin-Key) e não afeta outro tenant.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select


def cabecalho(tenant: dict) -> dict[str, str]:
    return {"X-API-Key": tenant["api_key"]}


async def _criar(cliente, slug: str) -> dict:
    resposta = await cliente.post("/v1/tenants", json={"slug": slug, "nome": f"{slug} LTDA"})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


@pytest.fixture
def admin(app_teste, monkeypatch):
    from app.core.config import Settings, get_settings

    conf = Settings(
        environment="test", nfse_adapter="mock", admin_habilitado=True, admin_api_key="k" * 32
    )
    app_teste.dependency_overrides[get_settings] = lambda: conf
    yield {"X-Admin-Key": conf.admin_api_key}
    app_teste.dependency_overrides.clear()


class TestExpiracao:
    async def test_chave_expirada_devolve_401_distinto(self, cliente, sessao_db) -> None:
        from app.db.models.tenant import Tenant

        tenant = await _criar(cliente, "exp-1")
        registro = (
            await sessao_db.execute(select(Tenant).where(Tenant.slug == "exp-1"))
        ).scalar_one()
        registro.api_key_expira_em = datetime.now(UTC) - timedelta(minutes=1)
        await sessao_db.commit()

        resposta = await cliente.get("/v1/me", headers=cabecalho(tenant))

        assert resposta.status_code == 401
        assert "expirada" in resposta.json()["detail"]

    async def test_chave_valida_continua_passando(self, cliente) -> None:
        tenant = await _criar(cliente, "exp-2")

        assert (await cliente.get("/v1/me", headers=cabecalho(tenant))).status_code == 200


class TestRevogacao:
    async def test_revogada_devolve_401_e_nao_volta(self, cliente, sessao_db, admin) -> None:
        tenant = await _criar(cliente, "rev-1")

        resposta = await cliente.post(
            f"/v1/admin/tenants/{tenant['id']}/revogar-chave", headers=admin
        )
        assert resposta.status_code == 204, resposta.text

        negado = await cliente.get("/v1/me", headers=cabecalho(tenant))
        assert negado.status_code == 401
        # A chave revogada **não** se distingue de chave desconhecida: o hash foi substituído por
        # valor aleatório, então ela nem casa na busca. Deliberado — revogar não deixa porta de
        # retorno por flip de flag. O que fica registrado é o carimbo de auditoria.
        from app.db.models.tenant import Tenant

        registro = (
            await sessao_db.execute(select(Tenant).where(Tenant.id == uuid.UUID(tenant["id"])))
        ).scalar_one()
        assert registro.api_key_revogada_em is not None
        assert registro.api_key_hash != tenant["api_key"]

    async def test_revogar_exige_admin(self, cliente) -> None:
        tenant = await _criar(cliente, "rev-2")

        resposta = await cliente.post(f"/v1/admin/tenants/{tenant['id']}/revogar-chave")

        # Sem admin habilitado a rota responde 404 (ADR 0001), não 401: ela "não existe".
        assert resposta.status_code == 404

    async def test_revogacao_nao_afeta_outro_tenant(self, cliente, admin) -> None:
        alvo = await _criar(cliente, "rev-3")
        vizinho = await _criar(cliente, "rev-4")

        await cliente.post(f"/v1/admin/tenants/{alvo['id']}/revogar-chave", headers=admin)

        assert (await cliente.get("/v1/me", headers=cabecalho(alvo))).status_code == 401
        assert (await cliente.get("/v1/me", headers=cabecalho(vizinho))).status_code == 200


class TestRotacaoComPrazo:
    async def test_rotacao_grava_validade_e_limpa_revogacao(
        self, cliente, sessao_db, admin
    ) -> None:
        from app.db.models.tenant import Tenant

        tenant = await _criar(cliente, "rot-1")
        await cliente.post(f"/v1/admin/tenants/{tenant['id']}/revogar-chave", headers=admin)

        registro = (
            await sessao_db.execute(select(Tenant).where(Tenant.slug == "rot-1"))
        ).scalar_one()
        assert registro.api_key_revogada_em is not None

        from app.tenants import service as tenant_service

        _, nova = await tenant_service.rotacionar_chave(
            sessao_db, uuid.UUID(tenant["id"]), dias_validade=30
        )
        await sessao_db.commit()

        registro = (
            await sessao_db.execute(select(Tenant).where(Tenant.slug == "rot-1"))
        ).scalar_one()
        assert registro.api_key_revogada_em is None, "chave nova não pode nascer revogada"
        assert registro.api_key_expira_em is not None

        # Chave nova funciona; a revogada continua morta.
        assert (await cliente.get("/v1/me", headers={"X-API-Key": nova})).status_code == 200
        assert (await cliente.get("/v1/me", headers=cabecalho(tenant))).status_code == 401
