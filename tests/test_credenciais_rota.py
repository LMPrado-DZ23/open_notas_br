"""Rotas de credencial municipal: auth, isolamento e sigilo do segredo."""

from __future__ import annotations

import base64

import pytest
from app.core.config import Settings, get_settings
from app.db.models.credencial_municipal import CredencialMunicipalTenant
from app.db.models.municipio import MunicipioNFSe, ProvedorNFSe
from sqlalchemy import select


@pytest.fixture
async def ambiente(cliente, app_teste, sessao_db):
    app_teste.dependency_overrides[get_settings] = lambda: Settings(
        environment="test",
        nfse_adapter="mock",
        master_encryption_key=base64.b64encode(b"k" * 32).decode(),
    )
    sessao_db.add(
        MunicipioNFSe(
            codigo_ibge="5200258",
            nome="Aguas Lindas de Goias",
            uf="GO",
            provedor=ProvedorNFSe.NACIONAL_REST,
            fonte_url="https://servicodados.ibge.gov.br/api/v1/localidades/municipios",
        )
    )
    await sessao_db.commit()

    criado = await cliente.post("/v1/tenants", json={"slug": "cred-a", "nome": "Cred A"})
    tenant = criado.json()
    yield {"cabecalho": {"X-API-Key": tenant["api_key"]}, "tenant_id": tenant["id"]}
    app_teste.dependency_overrides.clear()


class TestCriacao:
    async def test_cria_credencial(self, cliente, ambiente) -> None:
        resposta = await cliente.post(
            "/v1/credenciais-municipais",
            json={
                "codigo_ibge": "5200258",
                "inscricao_municipal": "12345",
                "usuario_ws": "user",
                "senha_ws": "senha",
            },
            headers=ambiente["cabecalho"],
        )
        assert resposta.status_code == 201, resposta.text
        corpo = resposta.json()
        assert corpo["tem_usuario"] is True
        assert corpo["tem_senha"] is True
        assert corpo["tem_token"] is False

    async def test_resposta_nunca_traz_o_segredo(self, cliente, ambiente) -> None:
        resposta = await cliente.post(
            "/v1/credenciais-municipais",
            json={"codigo_ibge": "5200258", "senha_ws": "segredo-que-nao-pode-vazar"},
            headers=ambiente["cabecalho"],
        )
        assert "segredo-que-nao-pode-vazar" not in resposta.text

    async def test_municipio_inexistente_da_404(self, cliente, ambiente) -> None:
        resposta = await cliente.post(
            "/v1/credenciais-municipais",
            json={"codigo_ibge": "9999999", "senha_ws": "x"},
            headers=ambiente["cabecalho"],
        )
        assert resposta.status_code == 404

    async def test_ibge_invalido_da_422(self, cliente, ambiente) -> None:
        resposta = await cliente.post(
            "/v1/credenciais-municipais",
            json={"codigo_ibge": "123", "senha_ws": "x"},
            headers=ambiente["cabecalho"],
        )
        assert resposta.status_code == 422


class TestIsolamento:
    async def test_lista_so_o_proprio_tenant(self, cliente, ambiente, sessao_db) -> None:
        await cliente.post(
            "/v1/credenciais-municipais",
            json={"codigo_ibge": "5200258", "senha_ws": "a"},
            headers=ambiente["cabecalho"],
        )
        outro = await cliente.post("/v1/tenants", json={"slug": "cred-b", "nome": "Cred B"})
        corpo = (
            await cliente.get(
                "/v1/credenciais-municipais", headers={"X-API-Key": outro.json()["api_key"]}
            )
        ).json()
        assert corpo["total"] == 0, "credencial de um tenant não aparece para outro"

    async def test_desativar_de_outro_tenant_da_404(self, cliente, ambiente) -> None:
        await cliente.post(
            "/v1/credenciais-municipais",
            json={"codigo_ibge": "5200258", "senha_ws": "a"},
            headers=ambiente["cabecalho"],
        )
        outro = await cliente.post("/v1/tenants", json={"slug": "cred-c", "nome": "Cred C"})
        resposta = await cliente.delete(
            "/v1/credenciais-municipais/5200258",
            headers={"X-API-Key": outro.json()["api_key"]},
        )
        assert resposta.status_code == 404

    async def test_sem_api_key_da_401_ou_403(self, cliente) -> None:
        assert (await cliente.get("/v1/credenciais-municipais")).status_code in (401, 403)


class TestDesativacao:
    async def test_desativa_sem_apagar(self, cliente, ambiente, sessao_db) -> None:
        await cliente.post(
            "/v1/credenciais-municipais",
            json={"codigo_ibge": "5200258", "senha_ws": "a"},
            headers=ambiente["cabecalho"],
        )
        resposta = await cliente.delete(
            "/v1/credenciais-municipais/5200258", headers=ambiente["cabecalho"]
        )
        assert resposta.status_code == 200
        assert resposta.json()["ativa"] is False

        # A linha continua no banco: apagar perderia a ligação com notas emitidas.
        linhas = (
            (
                await sessao_db.execute(
                    select(CredencialMunicipalTenant).where(
                        CredencialMunicipalTenant.codigo_ibge == "5200258"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(linhas) == 1
        assert linhas[0].ativa is False
