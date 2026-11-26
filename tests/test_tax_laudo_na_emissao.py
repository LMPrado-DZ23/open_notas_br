"""A emissão grava o laudo? Teste de integração com banco real.

Sem este teste, "ligado ao fluxo" seria afirmação sem prova: a suíte passaria mesmo que
a chamada fosse um no-op.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings, get_settings
from app.db.models.tax import CalculoAudit
from app.tax import auditoria_service as svc
from sqlalchemy import select

from tests.test_fase2_certificado import SENHA, gerar_pfx

CORPO = {
    "valor": "10.00",
    "descricao": "Servico para teste de laudo",
    "competencia": "2026-11",
    "municipio_ibge": "5200258",
}


@pytest.fixture
async def pronto(cliente, app_teste):
    criado = await cliente.post("/v1/tenants", json={"slug": "laudo-tenant", "nome": "Laudo LTDA"})
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
    yield {"cabecalho": cabecalho, "tenant_id": tenant["id"]}
    app_teste.dependency_overrides.clear()


class TestGravacao:
    async def test_emissao_grava_laudo(self, cliente, pronto, sessao_db) -> None:
        resposta = await cliente.post(
            "/v1/emissoes",
            json={**CORPO, "idempotency_key": "laudo-emissao-001"},
            headers=pronto["cabecalho"],
        )
        assert resposta.status_code == 201, resposta.text

        registros = (
            (
                await sessao_db.execute(
                    select(CalculoAudit).where(CalculoAudit.tenant_id == pronto["tenant_id"])
                )
            )
            .scalars()
            .all()
        )
        assert len(registros) == 1, "a emissão precisa gravar exatamente um laudo"

        laudo = registros[0]
        assert laudo.hash_laudo
        assert laudo.entrada["base_calculo"] == "10.00"
        assert laudo.data_emissao is not None
        assert laudo.trace_id, "trace_id liga laudo, documento e logs"
        assert await svc.verificar_integridade(laudo) is True

    async def test_reenvio_idempotente_nao_duplica_laudo(self, cliente, pronto, sessao_db) -> None:
        cabecalho = pronto["cabecalho"]
        primeiro = await cliente.post(
            "/v1/emissoes",
            json={**CORPO, "idempotency_key": "laudo-emissao-002"},
            headers=cabecalho,
        )
        segundo = await cliente.post(
            "/v1/emissoes",
            json={**CORPO, "idempotency_key": "laudo-emissao-002"},
            headers=cabecalho,
        )
        assert primeiro.status_code == 201
        assert segundo.status_code == 200

        registros = (
            (
                await sessao_db.execute(
                    select(CalculoAudit).where(CalculoAudit.tenant_id == pronto["tenant_id"])
                )
            )
            .scalars()
            .all()
        )
        assert len(registros) == 1, "reenvio não pode criar segundo laudo"
