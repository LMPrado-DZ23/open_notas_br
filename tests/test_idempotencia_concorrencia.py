"""Concorrência na idempotência: o que está provado e o que não está.

A garantia contra duas notas para o mesmo `Idempotency-Key` vem do banco: a constraint
`uq_invoices_tenant_idempotency_key`. O código trata `IntegrityError` buscando a fatura
existente. Isso é verificado **sequencialmente** aqui, que é o caminho que o cliente repete.

**O caso realmente simultâneo NÃO está provado** e o motivo está na auditoria §18: com duas
requisições concorrentes, o teste levanta `MissingGreenlet` dentro de `do_ping` do pool
(`pool_pre_ping`), não no código de emissão. Investigar isso exige um harness próprio; deixar
um teste que não entendo, ou marcar como "concorrência OK" sem entender, seria pior que a
ausência.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings, get_settings
from app.db.models.invoice import Invoice
from sqlalchemy import func, select

from tests.test_fase2_certificado import SENHA, gerar_pfx

CORPO = {
    "valor": "10.00",
    "descricao": "Servico de teste de idempotencia",
    "competencia": "2026-11",
    "municipio_ibge": "5200258",
}
CHAVE = "concorrente-0001-abcd"


@pytest.fixture
async def pronto(cliente, app_teste):
    criado = await cliente.post(
        "/v1/tenants", json={"slug": "conc-1", "nome": "Concorrencia LTDA"}
    )
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
    yield {"cabecalho": cabecalho, "tenant": tenant}
    app_teste.dependency_overrides.clear()


class TestRepeticaoSequencial:
    """O caminho que o cliente faz quando repete: 201 e depois 200, uma fatura só."""

    async def test_envio_repetido_nao_cria_segunda_fatura(
        self, cliente, pronto, sessao_db
    ) -> None:
        cabecalho = {**pronto["cabecalho"], "Idempotency-Key": CHAVE}

        primeira = await cliente.post("/v1/emissoes", json=CORPO, headers=cabecalho)
        segunda = await cliente.post("/v1/emissoes", json=CORPO, headers=cabecalho)

        assert primeira.status_code == 201, primeira.text
        assert segunda.status_code == 200, segunda.text
        assert primeira.json()["invoice_id"] == segunda.json()["invoice_id"], "cliente recebeu dois documentos"
        assert segunda.json().get("ja_existia") is True

        total = (
            await sessao_db.execute(
                select(func.count())
                .select_from(Invoice)
                .where(Invoice.idempotency_key == CHAVE)
            )
        ).scalar_one()
        assert total == 1

    async def test_chaves_diferentes_criam_faturas_diferentes(
        self, cliente, pronto, sessao_db
    ) -> None:
        a = await cliente.post(
            "/v1/emissoes", json=CORPO, headers={**pronto["cabecalho"], "Idempotency-Key": "chave-a-0001"}
        )
        b = await cliente.post(
            "/v1/emissoes", json=CORPO, headers={**pronto["cabecalho"], "Idempotency-Key": "chave-b-0002"}
        )
        assert a.status_code == 201, a.text
        assert b.status_code == 201, b.text
        assert a.json()["invoice_id"] != b.json()["invoice_id"]

        # A constraint é por (tenant, chave): chaves distintas não colidem.
        total = (
            await sessao_db.execute(
                select(func.count())
                .select_from(Invoice)
                .where(Invoice.idempotency_key.in_(["chave-a-0001", "chave-b-0002"]))
            )
        ).scalar_one()
        assert total == 2
