"""Testes de tenant: criação, credencial, rotação e isolamento.

O teste que mais importa aqui é o de isolamento: uma API key não pode alcançar
dado de outro tenant sob nenhuma rota. É a invariante que, se quebrar, transforma
o serviço em vazamento de dados fiscais entre empresas.
"""

from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.db.models.enums import StatusTenant
from app.db.models.tenant import Tenant
from app.db.session import obter_sessionmaker
from sqlalchemy import select


async def criar_tenant(cliente, slug: str = "barbearia-centro", **extra: Any) -> dict[str, Any]:
    corpo = {"slug": slug, "nome": "Barbearia Centro LTDA", **extra}
    resposta = await cliente.post("/v1/tenants", json=corpo)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def cabecalho(chave: str) -> dict[str, str]:
    return {"X-API-Key": chave}


class TestCriacao:
    async def test_cria_e_devolve_chave_uma_vez(self, cliente) -> None:
        dados = await criar_tenant(cliente)

        assert dados["slug"] == "barbearia-centro"
        assert dados["status"] == "active"
        assert dados["api_key"].startswith("nb_")
        assert dados["api_key_prefix"] == dados["api_key"][:11]
        assert "api_key_hash" not in dados, "hash nunca deve sair na resposta"

    async def test_slug_duplicado_da_409(self, cliente) -> None:
        await criar_tenant(cliente, slug="repetido")
        resposta = await cliente.post("/v1/tenants", json={"slug": "repetido", "nome": "Outra"})
        assert resposta.status_code == 409

    async def test_slug_invalido_da_422(self, cliente) -> None:
        resposta = await cliente.post(
            "/v1/tenants", json={"slug": "Com Espaço!", "nome": "Nome Teste"}
        )
        assert resposta.status_code == 422

    async def test_slug_e_normalizado_para_minusculas(self, cliente) -> None:
        resposta = await cliente.post(
            "/v1/tenants", json={"slug": "MAIUSCULO", "nome": "Nome Teste"}
        )
        assert resposta.status_code == 201
        assert resposta.json()["slug"] == "maiusculo"

    async def test_chave_nao_e_armazenada_em_claro(self, cliente, sessao_db) -> None:
        dados = await criar_tenant(cliente, slug="cofre")

        resultado = await sessao_db.execute(select(Tenant).where(Tenant.slug == "cofre"))
        tenant = resultado.scalar_one()

        assert tenant.api_key_hash != dados["api_key"]
        assert dados["api_key"] not in tenant.api_key_hash
        assert len(tenant.api_key_hash) == 64

    async def test_webhook_gera_segredo_selado(self, cliente, sessao_db) -> None:
        dados = await criar_tenant(
            cliente, slug="com-webhook", webhook_url="https://exemplo.test/hook"
        )
        assert dados["webhook_secret"]
        assert len(dados["webhook_secret"]) == 64

        resultado = await sessao_db.execute(select(Tenant).where(Tenant.slug == "com-webhook"))
        tenant = resultado.scalar_one()
        assert tenant.webhook_secret_selado
        # O segredo em claro não pode aparecer no blob selado.
        assert dados["webhook_secret"].encode() not in tenant.webhook_secret_selado

    async def test_sem_webhook_nao_gera_segredo(self, cliente) -> None:
        dados = await criar_tenant(cliente, slug="sem-webhook")
        assert dados["webhook_secret"] is None


class TestAutenticacao:
    async def test_sem_chave_da_401(self, cliente) -> None:
        resposta = await cliente.get("/v1/me")
        assert resposta.status_code == 401
        assert resposta.headers.get("WWW-Authenticate") == "ApiKey"

    async def test_chave_invalida_da_401(self, cliente) -> None:
        resposta = await cliente.get("/v1/me", headers=cabecalho("nb_chave_que_nao_existe"))
        assert resposta.status_code == 401

    async def test_chave_valida_retorna_o_proprio_tenant(self, cliente) -> None:
        dados = await criar_tenant(cliente, slug="autenticado")
        resposta = await cliente.get("/v1/me", headers=cabecalho(dados["api_key"]))

        assert resposta.status_code == 200
        assert resposta.json()["slug"] == "autenticado"
        assert resposta.json()["id"] == dados["id"]

    async def test_tenant_suspenso_da_403(self, cliente) -> None:
        dados = await criar_tenant(cliente, slug="suspenso")

        fabrica = obter_sessionmaker()
        async with fabrica() as sessao:
            resultado = await sessao.execute(select(Tenant).where(Tenant.slug == "suspenso"))
            tenant = resultado.scalar_one()
            tenant.status = StatusTenant.SUSPENSO
            await sessao.commit()

        resposta = await cliente.get("/v1/me", headers=cabecalho(dados["api_key"]))
        assert resposta.status_code == 403


class TestIsolamento:
    async def test_dois_tenants_nao_se_enxergam(self, cliente) -> None:
        a = await criar_tenant(cliente, slug="tenant-a")
        b = await criar_tenant(cliente, slug="tenant-b")

        resposta_a = await cliente.get("/v1/me", headers=cabecalho(a["api_key"]))
        resposta_b = await cliente.get("/v1/me", headers=cabecalho(b["api_key"]))

        assert resposta_a.json()["id"] == a["id"]
        assert resposta_b.json()["id"] == b["id"]
        assert resposta_a.json()["id"] != resposta_b.json()["id"]

    async def test_config_fiscal_nao_vaza_entre_tenants(self, cliente) -> None:
        a = await criar_tenant(cliente, slug="config-a")
        b = await criar_tenant(cliente, slug="config-b")

        corpo = {"municipio_ibge": "3550308", "municipio_nome": "São Paulo", "uf": "sp"}
        criado = await cliente.put(
            "/v1/me/config-fiscal", json=corpo, headers=cabecalho(a["api_key"])
        )
        assert criado.status_code == 200, criado.text
        assert criado.json()["tenant_id"] == a["id"]

        do_b = await cliente.get("/v1/me/config-fiscal", headers=cabecalho(b["api_key"]))
        assert do_b.status_code == 200
        assert do_b.json() == []

        do_a = await cliente.get("/v1/me/config-fiscal", headers=cabecalho(a["api_key"]))
        assert len(do_a.json()) == 1
        assert do_a.json()[0]["uf"] == "SP"

    async def test_upsert_de_config_nao_duplica(self, cliente) -> None:
        dados = await criar_tenant(cliente, slug="upsert")
        chave = cabecalho(dados["api_key"])

        primeiro = await cliente.put(
            "/v1/me/config-fiscal",
            json={"municipio_ibge": "3550308", "regime_tributario": 1},
            headers=chave,
        )
        segundo = await cliente.put(
            "/v1/me/config-fiscal",
            json={"municipio_ibge": "3550308", "regime_tributario": 3},
            headers=chave,
        )

        assert primeiro.json()["id"] == segundo.json()["id"]
        assert segundo.json()["regime_tributario"] == 3

        listagem = await cliente.get("/v1/me/config-fiscal", headers=chave)
        assert len(listagem.json()) == 1


class TestRotacao:
    async def test_rotacao_invalida_chave_antiga(self, cliente) -> None:
        dados = await criar_tenant(cliente, slug="rotacao")
        antiga = dados["api_key"]

        resposta = await cliente.post("/v1/me/rotacionar-chave", headers=cabecalho(antiga))
        assert resposta.status_code == 200
        nova = resposta.json()["api_key"]
        assert nova != antiga

        assert (await cliente.get("/v1/me", headers=cabecalho(antiga))).status_code == 401
        assert (await cliente.get("/v1/me", headers=cabecalho(nova))).status_code == 200


class TestAdministrativo:
    async def test_listagem_paginada(self, cliente) -> None:
        await criar_tenant(cliente, slug="lista-1")
        await criar_tenant(cliente, slug="lista-2")

        resposta = await cliente.get("/v1/tenants?limite=1")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["total"] == 2
        assert len(corpo["itens"]) == 1
        assert corpo["limite"] == 1

    async def test_token_administrativo_obrigatorio_quando_configurado(
        self, app_teste, cliente
    ) -> None:
        app_teste.dependency_overrides[get_settings] = lambda: Settings(
            admin_api_token="segredo-admin", environment="test"
        )
        try:
            sem_token = await cliente.post(
                "/v1/tenants", json={"slug": "sem-token", "nome": "Nome Teste"}
            )
            assert sem_token.status_code == 403

            token_errado = await cliente.post(
                "/v1/tenants",
                json={"slug": "token-errado", "nome": "Nome Teste"},
                headers={"X-Admin-Token": "outro"},
            )
            assert token_errado.status_code == 403

            correto = await cliente.post(
                "/v1/tenants",
                json={"slug": "token-correto", "nome": "Nome Teste"},
                headers={"X-Admin-Token": "segredo-admin"},
            )
            assert correto.status_code == 201
        finally:
            app_teste.dependency_overrides.clear()


class TestOpenAPI:
    async def test_openapi_cobre_as_rotas_da_fase(self, cliente) -> None:
        resposta = await cliente.get("/openapi.json")
        assert resposta.status_code == 200
        caminhos = set(resposta.json()["paths"])
        esperados = {
            "/health",
            "/health/live",
            "/version",
            "/v1/tenants",
            "/v1/me",
            "/v1/me/rotacionar-chave",
            "/v1/me/config-fiscal",
        }
        assert esperados <= caminhos
