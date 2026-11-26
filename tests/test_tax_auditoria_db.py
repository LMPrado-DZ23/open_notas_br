"""Persistência do laudo de cálculo contra banco real.

Testes de integração: usam `sessao_db` (Postgres do compose), não mock. Um teste de
persistência com mock provaria apenas que o mock foi chamado.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.db.models.tax import CalculoAudit
from app.db.models.tenant import Tenant
from app.tax import auditoria_service as svc
from app.tax.auditoria import LaudoCalculo, TabelaConsultada
from sqlalchemy import select


async def criar_tenant(sessao, slug: str) -> Tenant:
    """Tenant mínimo válido.

    `api_key_prefix`/`api_key_hash` são NOT NULL no modelo — a API key é obrigatória
    na criação, não gerada depois. Um tenant sem credencial não poderia ser usado.
    """
    tenant = Tenant(
        slug=slug,
        nome=f"Tenant {slug}",
        api_key_prefix=slug[:8],
        api_key_hash=f"hash-{slug}"[:16].ljust(16, "0"),
    )
    sessao.add(tenant)
    await sessao.flush()
    return tenant


def laudo(**extra) -> LaudoCalculo:
    base = dict(
        entrada={"base": Decimal("100.00"), "uf": "GO"},
        saida={"iss": Decimal("5.00")},
        regras=("ISS alíquota 5%",),
        tabelas=(TabelaConsultada("iss", "2026.1", date(2026, 1, 1)),),
        data_emissao=date(2026, 11, 25),
        trace_id="trace-abc",
    )
    base.update(extra)
    return LaudoCalculo(**base)


class TestPersistencia:
    async def test_grava_e_le_por_trace(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "t-audit-1")
        registro = await svc.registrar(sessao_db, tenant_id=tenant.id, laudo=laudo())
        await sessao_db.commit()

        lidos = await svc.por_trace(sessao_db, tenant_id=tenant.id, trace_id="trace-abc")
        assert len(lidos) == 1
        assert lidos[0].id == registro.id

    async def test_guarda_conteudo_e_nao_so_hash(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "t-audit-2")
        await svc.registrar(sessao_db, tenant_id=tenant.id, laudo=laudo())
        await sessao_db.commit()

        lido = (await svc.por_trace(sessao_db, tenant_id=tenant.id, trace_id="trace-abc"))[0]
        assert lido.entrada["base"] == "100.00"
        assert lido.saida["iss"] == "5.00"
        assert lido.regras == ["ISS alíquota 5%"]
        assert lido.tabelas[0]["versao"] == "2026.1"
        assert lido.data_emissao == date(2026, 11, 25)

    async def test_hashes_gravados_batem_com_o_laudo(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "t-audit-3")
        original = laudo()
        await svc.registrar(sessao_db, tenant_id=tenant.id, laudo=original)
        await sessao_db.commit()

        lido = (await svc.por_trace(sessao_db, tenant_id=tenant.id, trace_id="trace-abc"))[0]
        assert lido.hash_entrada == original.hash_entrada
        assert lido.hash_saida == original.hash_saida
        assert lido.hash_laudo == original.hash_laudo

    async def test_integridade_recalculada_confere(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "t-audit-4")
        await svc.registrar(sessao_db, tenant_id=tenant.id, laudo=laudo())
        await sessao_db.commit()

        lido = (await svc.por_trace(sessao_db, tenant_id=tenant.id, trace_id="trace-abc"))[0]
        assert await svc.verificar_integridade(lido) is True

    async def test_integridade_detecta_edicao_direta(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "t-audit-5")
        await svc.registrar(sessao_db, tenant_id=tenant.id, laudo=laudo())
        await sessao_db.commit()

        registro = (
            await sessao_db.execute(select(CalculoAudit).where(CalculoAudit.tenant_id == tenant.id))
        ).scalar_one()
        # Simula edição por SQL manual no banco.
        registro.saida = {"iss": "99.00"}
        await sessao_db.flush()
        assert await svc.verificar_integridade(registro) is False

    async def test_mais_de_um_calculo_no_mesmo_trace(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "t-audit-6")
        await svc.registrar(sessao_db, tenant_id=tenant.id, laudo=laudo())
        await svc.registrar(
            sessao_db, tenant_id=tenant.id, laudo=laudo(saida={"icms": Decimal("18.00")})
        )
        await sessao_db.commit()
        assert len(await svc.por_trace(sessao_db, tenant_id=tenant.id, trace_id="trace-abc")) == 2

    async def test_sem_trace_nao_aparece_na_busca_por_trace(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "t-audit-7")
        await svc.registrar(sessao_db, tenant_id=tenant.id, laudo=laudo(trace_id=None))
        await sessao_db.commit()
        assert await svc.por_trace(sessao_db, tenant_id=tenant.id, trace_id="trace-abc") == []


class TestIsolamento:
    async def test_trace_de_outro_tenant_nao_aparece(self, sessao_db) -> None:
        a = await criar_tenant(sessao_db, "t-iso-a")
        b = await criar_tenant(sessao_db, "t-iso-b")
        await svc.registrar(sessao_db, tenant_id=a.id, laudo=laudo())
        await sessao_db.commit()

        assert await svc.por_trace(sessao_db, tenant_id=b.id, trace_id="trace-abc") == []

    async def test_por_id_de_outro_tenant_devolve_none(self, sessao_db) -> None:
        a = await criar_tenant(sessao_db, "t-iso-c")
        b = await criar_tenant(sessao_db, "t-iso-d")
        registro = await svc.registrar(sessao_db, tenant_id=a.id, laudo=laudo())
        await sessao_db.commit()

        assert await svc.por_id(sessao_db, tenant_id=b.id, registro_id=registro.id) is None
        assert (
            await svc.por_id(sessao_db, tenant_id=a.id, registro_id=registro.id)
        ).id == registro.id

    async def test_id_inexistente_devolve_none(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "t-iso-e")
        assert await svc.por_id(sessao_db, tenant_id=tenant.id, registro_id=uuid.uuid4()) is None
