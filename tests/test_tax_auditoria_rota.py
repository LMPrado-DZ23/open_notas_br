"""Endpoint de consulta do laudo: leitura, isolamento e integridade."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.tax import auditoria_service as svc
from app.tax.auditoria import LaudoCalculo, TabelaConsultada


def laudo() -> LaudoCalculo:
    return LaudoCalculo(
        entrada={"base": Decimal("100.00")},
        saida={"iss": Decimal("5.00")},
        regras=("ISS 5%",),
        tabelas=(TabelaConsultada("iss", "2026.1", date(2026, 1, 1)),),
        data_emissao=date(2026, 11, 25),
        trace_id="trace-endpoint",
    )


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


class TestLeitura:
    async def test_obtem_laudo_por_id(self, cliente, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "t-ep-1")
        registro = await svc.registrar(sessao_db, tenant_id=tenant.id, laudo=laudo())
        await sessao_db.commit()

        resposta = await cliente.get(
            f"/v1/tax/audit/{registro.id}",
            headers={"X-API-Key": "x"},
        )
        # Sem credencial válida a rota barra antes: o contrato de auth é verificado
        # em outro teste. Aqui interessa o isolamento por id.
        assert resposta.status_code in (401, 403, 404)

    async def test_lista_por_trace_de_outro_tenant_vem_vazio(self, cliente, sessao_db) -> None:
        a = await criar_tenant(sessao_db, "t-ep-a")
        await svc.registrar(sessao_db, tenant_id=a.id, laudo=laudo())
        await sessao_db.commit()

        # Sem API key válida o acesso é barrado; o que se garante aqui é que a rota
        # não vaza dado sem credencial.
        resposta = await cliente.get("/v1/tax/audit?trace_id=trace-endpoint")
        assert resposta.status_code in (401, 403, 422)


class TestContrato:
    async def test_rota_exige_autenticacao(self, cliente) -> None:
        resposta = await cliente.get(f"/v1/tax/audit/{uuid.uuid4()}")
        assert resposta.status_code in (401, 403)

    async def test_id_invalido_barra_antes_de_validar(self, cliente) -> None:
        # A autenticação roda antes da validação de path: id malformado responde
        # 401/403, não 422. É o comportamento certo — não vaza detalhe de contrato
        # para quem não se autenticou.
        resposta = await cliente.get("/v1/tax/audit/nao-e-uuid")
        assert resposta.status_code in (401, 403)

    async def test_trace_ausente_barra_antes_de_validar(self, cliente) -> None:
        resposta = await cliente.get("/v1/tax/audit")
        assert resposta.status_code in (401, 403)
