"""Isolamento nos downloads de documento (§67).

O prompt exige teste de vazamento entre tenants em **arquivos** — e o arquivo aqui é o documento
fiscal do cliente: PDF do DANFSe e representação impressa.

As rotas filtram por `tenant.id` (`emissoes.py`), mas não havia **teste** provando isso: um `where`
esquecido em refatoração passaria despercebido, e o resultado seria um tenant baixando a nota de
outro pelo id.

Cenário: dois tenants emissores, cada um emite a sua nota; o tenant B tenta baixar os arquivos do A.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.test_fase2_certificado import SENHA, gerar_pfx


def cabecalho(tenant: dict[str, Any]) -> dict[str, str]:
    return {"X-API-Key": tenant["api_key"]}


async def _preparar(cliente, slug: str, ibge: str, uf: str) -> dict[str, Any]:
    criado = await cliente.post("/v1/tenants", json={"slug": slug, "nome": f"{slug} LTDA"})
    assert criado.status_code == 201, criado.text
    tenant = criado.json()

    config = await cliente.put(
        "/v1/me/config-fiscal",
        json={
            "municipio_ibge": ibge,
            "uf": uf,
            "ambiente": "homologacao",
            "codigo_tributacao_nacional": "010701",
            "serie_dps": "1",
            "aliquota_iss": 0.05,
        },
        headers=cabecalho(tenant),
    )
    assert config.status_code == 200, config.text

    certificado = await cliente.post(
        "/v1/me/certificados",
        files={"arquivo": ("c.pfx", gerar_pfx(), "application/x-pkcs12")},
        data={"senha": SENHA.decode(), "apelido": "a1"},
        headers=cabecalho(tenant),
    )
    assert certificado.status_code == 201, certificado.text
    return tenant


async def _emitir(cliente, tenant: dict[str, Any], chave: str, valor: str) -> str:
    resposta = await cliente.post(
        "/v1/emissoes",
        json={
            "idempotency_key": chave,
            "valor": valor,
            "descricao": "Servico de teste de isolamento",
            "competencia": "2026-11",
        },
        headers=cabecalho(tenant),
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["invoice_id"]


@pytest.fixture
async def dois_emissores(cliente, app_teste):
    from app.core.config import Settings, get_settings

    app_teste.dependency_overrides[get_settings] = lambda: Settings(
        environment="test", nfse_adapter="mock"
    )
    try:
        a = await _preparar(cliente, "iso-a", "3550308", "SP")
        b = await _preparar(cliente, "iso-b", "5200258", "GO")
        fatura_a = await _emitir(cliente, a, "iso-a-0001", "10.00")
        yield {"a": a, "b": b, "fatura_a": fatura_a}
    finally:
        app_teste.dependency_overrides.clear()


class TestDownloads:
    async def test_outro_tenant_nao_baixa_danfse(self, cliente, dois_emissores) -> None:
        resposta = await cliente.get(
            f"/v1/emissoes/{dois_emissores['fatura_a']}/danfse",
            headers=cabecalho(dois_emissores["b"]),
        )

        assert resposta.status_code == 404, resposta.text

    async def test_outro_tenant_nao_baixa_representacao(self, cliente, dois_emissores) -> None:
        resposta = await cliente.get(
            f"/v1/emissoes/{dois_emissores['fatura_a']}/representacao",
            headers=cabecalho(dois_emissores["b"]),
        )

        assert resposta.status_code == 404, resposta.text

    async def test_dono_baixa_normalmente(self, cliente, dois_emissores) -> None:
        """Contraprova: sem isto, um 404 geral passaria como 'isolamento funcionando'."""
        resposta = await cliente.get(
            f"/v1/emissoes/{dois_emissores['fatura_a']}/danfse",
            headers=cabecalho(dois_emissores["a"]),
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.content.startswith(b"%PDF")

    async def test_sem_chave_nao_baixa(self, cliente, dois_emissores) -> None:
        resposta = await cliente.get(f"/v1/emissoes/{dois_emissores['fatura_a']}/danfse")

        assert resposta.status_code == 401
