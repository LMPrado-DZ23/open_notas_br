"""Idempotência por header, compatível com o campo do body (Etapa A).

O que se verifica aqui é o que quebra em produção: cliente antigo que só manda o
body, cliente novo que só manda o header, os dois divergindo, e nenhum dos dois.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings, get_settings

from tests.test_fase2_certificado import SENHA, gerar_pfx

CORPO = {
    "valor": "10.00",
    "descricao": "Servico de teste de idempotencia",
    "competencia": "2026-11",
    "municipio_ibge": "5200258",
}


@pytest.fixture
async def pronto(cliente, app_teste):
    criado = await cliente.post("/v1/tenants", json={"slug": "idem-tenant", "nome": "Idem LTDA"})
    tenant = criado.json()
    cabecalho = {"X-API-Key": tenant["api_key"]}

    app_teste.dependency_overrides[get_settings] = lambda: Settings(
        environment="test", nfse_adapter="mock"
    )
    await cliente.put(
        "/v1/me/config-fiscal",
        json={
            "municipio_ibge": "5200258",
            "uf": "GO",
            "ambiente": "homologacao",
            "codigo_tributacao_nacional": "010501",
            "serie_dps": "1",
            "aliquota_iss": 0.05,
            "simples_nacional": False,
        },
        headers=cabecalho,
    )
    await cliente.post(
        "/v1/me/certificados",
        files={"arquivo": ("c.pfx", gerar_pfx(), "application/x-pkcs12")},
        data={"senha": SENHA.decode(), "apelido": "a1"},
        headers=cabecalho,
    )
    yield {"cabecalho": cabecalho}
    app_teste.dependency_overrides.clear()


class TestCompatibilidade:
    async def test_so_body_continua_funcionando(self, cliente, pronto) -> None:
        """Cliente antigo: nenhuma mudança de contrato."""
        resposta = await cliente.post(
            "/v1/emissoes",
            json={**CORPO, "idempotency_key": "idem-body-001"},
            headers=pronto["cabecalho"],
        )
        assert resposta.status_code == 201, resposta.text

    async def test_so_header_funciona(self, cliente, pronto) -> None:
        cabecalho = {**pronto["cabecalho"], "Idempotency-Key": "idem-header-001"}
        resposta = await cliente.post("/v1/emissoes", json=CORPO, headers=cabecalho)
        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["idempotency_key"] == "idem-header-001"

    async def test_reenvio_com_mesmo_header_nao_duplica(self, cliente, pronto) -> None:
        cabecalho = {**pronto["cabecalho"], "Idempotency-Key": "idem-header-002"}
        primeira = await cliente.post("/v1/emissoes", json=CORPO, headers=cabecalho)
        segunda = await cliente.post("/v1/emissoes", json=CORPO, headers=cabecalho)
        assert primeira.status_code == 201
        assert segunda.status_code == 200, "duplicata devolve a emissão existente"
        assert segunda.json()["ja_existia"] is True
        assert primeira.json()["invoice_id"] == segunda.json()["invoice_id"]


class TestPrecedencia:
    async def test_header_vence_o_body(self, cliente, pronto) -> None:
        # Escolher o body permitiria que um header injetado por proxy mudasse a
        # chave sem o cliente perceber.
        cabecalho = {**pronto["cabecalho"], "Idempotency-Key": "idem-header-vence"}
        resposta = await cliente.post(
            "/v1/emissoes",
            json={**CORPO, "idempotency_key": "idem-body-perde"},
            headers=cabecalho,
        )
        assert resposta.status_code == 201
        assert resposta.json()["idempotency_key"] == "idem-header-vence"


class TestAusencia:
    async def test_sem_chave_nenhuma_da_422(self, cliente, pronto) -> None:
        resposta = await cliente.post("/v1/emissoes", json=CORPO, headers=pronto["cabecalho"])
        assert resposta.status_code == 422
        assert "Idempotency-Key" in resposta.json()["detail"]

    async def test_chave_curta_no_header_da_422(self, cliente, pronto) -> None:
        cabecalho = {**pronto["cabecalho"], "Idempotency-Key": "curta"}
        resposta = await cliente.post("/v1/emissoes", json=CORPO, headers=cabecalho)
        assert resposta.status_code == 422
