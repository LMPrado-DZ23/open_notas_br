"""Concorrência na idempotência: repetição sequencial e simultaneidade.

A garantia contra duas notas para o mesmo `Idempotency-Key` tem duas camadas:

1. **advisory lock** por (tenant, chave), adquirido antes de consultar — evita a corrida;
2. **constraint** `uq_invoices_tenant_idempotency_key` — rede de segurança se a camada 1 falhar.

Histórico: até 2026-11-27 o caso simultâneo **não estava provado** — o teste levantava
`MissingGreenlet` dentro de `do_ping`/`_handle_exception` do driver, e o docstring dizia que
investigar exigiria um harness próprio. A investigação mostrou que **não era artefato de teste**:
sem a trava, as duas requisições passavam pela checagem, as duas inseriam, e a recuperação do
`IntegrityError` estourava com `MissingGreenlet` — o cliente recebia **500** num caminho que
deveria ser 200 (auditoria §55). O caso agora está coberto e passa.
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
    criado = await cliente.post("/v1/tenants", json={"slug": "conc-1", "nome": "Concorrencia LTDA"})
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

    async def test_envio_repetido_nao_cria_segunda_fatura(self, cliente, pronto, sessao_db) -> None:
        cabecalho = {**pronto["cabecalho"], "Idempotency-Key": CHAVE}

        primeira = await cliente.post("/v1/emissoes", json=CORPO, headers=cabecalho)
        segunda = await cliente.post("/v1/emissoes", json=CORPO, headers=cabecalho)

        assert primeira.status_code == 201, primeira.text
        assert segunda.status_code == 200, segunda.text
        assert primeira.json()["invoice_id"] == segunda.json()["invoice_id"], (
            "cliente recebeu dois documentos"
        )
        assert segunda.json().get("ja_existia") is True

        total = (
            await sessao_db.execute(
                select(func.count()).select_from(Invoice).where(Invoice.idempotency_key == CHAVE)
            )
        ).scalar_one()
        assert total == 1

    async def test_chaves_diferentes_criam_faturas_diferentes(
        self, cliente, pronto, sessao_db
    ) -> None:
        a = await cliente.post(
            "/v1/emissoes",
            json=CORPO,
            headers={**pronto["cabecalho"], "Idempotency-Key": "chave-a-0001"},
        )
        b = await cliente.post(
            "/v1/emissoes",
            json=CORPO,
            headers={**pronto["cabecalho"], "Idempotency-Key": "chave-b-0002"},
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


class TestSimultaneidade:
    """Duas requisições **ao mesmo tempo** com a mesma `Idempotency-Key`.

    O docstring deste arquivo dizia que este caso não estava provado por causa de um
    `MissingGreenlet` em `do_ping` do pool. Um erro de pool em requisições concorrentes pode ser
    do harness de teste **ou** do produto — e a diferença importa: em produção o cliente repete
    em rede instável, e duas notas para o mesmo pedido é o pior defeito possível aqui.
    """

    async def test_duas_requisicoes_simultaneas_criam_uma_fatura(
        self, cliente, pronto, sessao_db
    ) -> None:
        import asyncio

        cabecalho = {**pronto["cabecalho"], "Idempotency-Key": "simultanea-0001"}

        respostas = await asyncio.gather(
            cliente.post("/v1/emissoes", json=CORPO, headers=cabecalho),
            cliente.post("/v1/emissoes", json=CORPO, headers=cabecalho),
            return_exceptions=True,
        )

        codigos = [r.status_code if hasattr(r, "status_code") else repr(r) for r in respostas]
        assert all(not isinstance(r, BaseException) for r in respostas), (
            f"requisicao concorrente estourou: {codigos}"
        )

        # Uma cria (201) e a outra reaproveita (200). Nenhuma pode ser 5xx.
        assert sorted(r.status_code for r in respostas) == [200, 201], codigos

        total = (
            await sessao_db.execute(
                select(func.count())
                .select_from(Invoice)
                .where(Invoice.idempotency_key == "simultanea-0001")
            )
        ).scalar_one()
        assert total == 1, "duas faturas para o mesmo Idempotency-Key"
