"""Tarefa com retry e DLQ: quem retenta, quem não retenta e o que fica registrado."""

from __future__ import annotations

import pytest
from app.db.models.dlq import ItemDLQ, StatusDLQ
from app.db.models.tenant import Tenant
from app.worker.tarefas import executar_com_dlq
from sqlalchemy import select


async def criar_tenant(sessao, slug: str) -> Tenant:
    tenant = Tenant(
        slug=slug,
        nome=f"Tenant {slug}",
        api_key_prefix=slug[:8],
        api_key_hash=f"hash-{slug}"[:16].ljust(16, "0"),
    )
    sessao.add(tenant)
    await sessao.flush()
    return tenant


class FalhaTransitoria(Exception):
    pass


class TestSucesso:
    async def test_sucesso_nao_grava_dlq(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "t-ok")

        async def tarefa() -> str:
            return "feito"

        resultado = await executar_com_dlq(
            sessao_db,
            tenant_id=tenant.id,
            fila="emitir",
            payload={"x": 1},
            tarefa=tarefa,
            erros_transitorios=(FalhaTransitoria,),
        )
        await sessao_db.commit()

        assert resultado.ok is True
        assert resultado.valor == "feito"
        assert resultado.dlq_id is None
        itens = (
            (await sessao_db.execute(select(ItemDLQ).where(ItemDLQ.tenant_id == tenant.id)))
            .scalars()
            .all()
        )
        assert itens == [], "sucesso não pode virar log na DLQ"

    async def test_sucesso_apos_falha_transitoria(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "t-retry")
        chamadas = 0

        async def tarefa() -> str:
            nonlocal chamadas
            chamadas += 1
            if chamadas < 3:
                raise FalhaTransitoria("instavel")
            return "ok"

        resultado = await executar_com_dlq(
            sessao_db,
            tenant_id=tenant.id,
            fila="emitir",
            payload={},
            tarefa=tarefa,
            tentativas=3,
            erros_transitorios=(FalhaTransitoria,),
        )
        await sessao_db.commit()
        assert resultado.ok is True
        assert resultado.tentativas == 3
        assert chamadas == 3


class TestFalhaPersistente:
    async def test_esgotar_tentativas_vai_para_dlq(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "t-dlq")

        async def sempre_falha() -> str:
            raise FalhaTransitoria("SEFAZ fora")

        resultado = await executar_com_dlq(
            sessao_db,
            tenant_id=tenant.id,
            fila="emitir",
            payload={"chave": "abc"},
            tarefa=sempre_falha,
            tentativas=2,
            trace_id="tr-1",
            erros_transitorios=(FalhaTransitoria,),
        )
        await sessao_db.commit()

        assert resultado.ok is False
        assert resultado.tentativas == 2
        assert resultado.dlq_id is not None

        item = (
            await sessao_db.execute(select(ItemDLQ).where(ItemDLQ.id == resultado.dlq_id))
        ).scalar_one()
        assert item.status is StatusDLQ.PENDENTE
        assert item.payload == {"chave": "abc"}, "payload original preservado"
        assert item.trace_id == "tr-1"
        assert "SEFAZ fora" in item.erro

    async def test_erro_definitivo_nao_retenta(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "t-def")
        chamadas = 0

        async def rejeita() -> str:
            nonlocal chamadas
            chamadas += 1
            raise ValueError("rejeição 539")

        resultado = await executar_com_dlq(
            sessao_db,
            tenant_id=tenant.id,
            fila="emitir",
            payload={},
            tarefa=rejeita,
            tentativas=5,
            erros_transitorios=(FalhaTransitoria,),
        )
        await sessao_db.commit()

        # Retentar rejeição não muda o resultado e queima cota do autorizador.
        assert chamadas == 1, "erro definitivo não pode ser retentado"
        assert resultado.tentativas == 1
        assert resultado.dlq_id is not None

    async def test_timeout_e_transitorio(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "t-to")
        chamadas = 0

        async def estoura() -> str:
            nonlocal chamadas
            chamadas += 1
            raise TimeoutError

        resultado = await executar_com_dlq(
            sessao_db,
            tenant_id=tenant.id,
            fila="emitir",
            payload={},
            tarefa=estoura,
            tentativas=2,
        )
        await sessao_db.commit()
        assert chamadas == 2
        assert resultado.ok is False


class TestConfiguracao:
    async def test_tentativas_zero_recusado(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "t-cfg")

        async def noop() -> None:
            return None

        with pytest.raises(ValueError, match="tentativas"):
            await executar_com_dlq(
                sessao_db,
                tenant_id=tenant.id,
                fila="f",
                payload={},
                tarefa=noop,
                tentativas=0,
            )
