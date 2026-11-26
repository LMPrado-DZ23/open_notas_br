"""DLQ: enfileirar, isolamento, replay único e falha de replay."""

from __future__ import annotations

import uuid

import pytest
from app.db.models.dlq import StatusDLQ
from app.db.models.tenant import Tenant
from app.worker import dlq as svc


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


class TestEnfileirar:
    async def test_guarda_payload_original(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "d-1")
        item = await svc.enfileirar(
            sessao_db,
            tenant_id=tenant.id,
            fila="emitir_nfse",
            payload={"valor": "10.00", "municipio": "5200258"},
            erro="timeout",
            trace_id="tr-1",
        )
        await sessao_db.commit()
        assert item.payload["municipio"] == "5200258"
        assert item.status is StatusDLQ.PENDENTE
        assert item.tentativas == 0

    async def test_erro_gigante_e_truncado(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "d-2")
        item = await svc.enfileirar(
            sessao_db, tenant_id=tenant.id, fila="f", payload={}, erro="x" * 9000
        )
        assert len(item.erro) == 4000


class TestListagem:
    async def test_lista_so_pendentes_por_padrao(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "d-3")
        a = await svc.enfileirar(sessao_db, tenant_id=tenant.id, fila="f", payload={})
        await svc.enfileirar(sessao_db, tenant_id=tenant.id, fila="f", payload={})
        await svc.descartar(sessao_db, tenant_id=tenant.id, item_id=a.id)
        await sessao_db.commit()

        pendentes = await svc.listar(sessao_db, tenant_id=tenant.id)
        assert len(pendentes) == 1

    async def test_filtra_por_fila(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "d-4")
        await svc.enfileirar(sessao_db, tenant_id=tenant.id, fila="webhook", payload={})
        await svc.enfileirar(sessao_db, tenant_id=tenant.id, fila="emitir", payload={})
        await sessao_db.commit()
        assert len(await svc.listar(sessao_db, tenant_id=tenant.id, fila="webhook")) == 1


class TestReplay:
    async def test_replay_marca_e_incrementa(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "d-5")
        item = await svc.enfileirar(sessao_db, tenant_id=tenant.id, fila="f", payload={})
        await sessao_db.commit()

        preparado = await svc.preparar_replay(sessao_db, tenant_id=tenant.id, item_id=item.id)
        await sessao_db.commit()
        assert preparado.status is StatusDLQ.REPROCESSADO
        assert preparado.tentativas == 1
        assert preparado.reprocessado_em is not None

    async def test_replay_duplo_recusado(self, sessao_db) -> None:
        # Replay duplo reenviaria a mesma nota: a falha mais cara possível aqui.
        tenant = await criar_tenant(sessao_db, "d-6")
        item = await svc.enfileirar(sessao_db, tenant_id=tenant.id, fila="f", payload={})
        await svc.preparar_replay(sessao_db, tenant_id=tenant.id, item_id=item.id)
        await sessao_db.commit()

        with pytest.raises(svc.ErroDLQ, match="já foi reprocessado"):
            await svc.preparar_replay(sessao_db, tenant_id=tenant.id, item_id=item.id)

    async def test_replay_de_descartado_recusado(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "d-7")
        item = await svc.enfileirar(sessao_db, tenant_id=tenant.id, fila="f", payload={})
        await svc.descartar(sessao_db, tenant_id=tenant.id, item_id=item.id)
        await sessao_db.commit()
        with pytest.raises(svc.ErroDLQ, match="descartado"):
            await svc.preparar_replay(sessao_db, tenant_id=tenant.id, item_id=item.id)

    async def test_falha_de_replay_volta_para_pendente(self, sessao_db) -> None:
        # Sem isto, replay que falhou ficaria marcado como sucesso e o trabalho se
        # perderia em silêncio.
        tenant = await criar_tenant(sessao_db, "d-8")
        item = await svc.enfileirar(sessao_db, tenant_id=tenant.id, fila="f", payload={})
        await svc.preparar_replay(sessao_db, tenant_id=tenant.id, item_id=item.id)
        await svc.marcar_replay_falhou(
            sessao_db, tenant_id=tenant.id, item_id=item.id, erro="SEFAZ fora"
        )
        await sessao_db.commit()
        assert item.status is StatusDLQ.PENDENTE
        assert item.erro == "SEFAZ fora"


class TestIsolamento:
    async def test_item_de_outro_tenant_invisivel(self, sessao_db) -> None:
        a = await criar_tenant(sessao_db, "d-a")
        b = await criar_tenant(sessao_db, "d-b")
        item = await svc.enfileirar(sessao_db, tenant_id=a.id, fila="f", payload={})
        await sessao_db.commit()

        assert await svc.listar(sessao_db, tenant_id=b.id) == []
        assert await svc.por_id(sessao_db, tenant_id=b.id, item_id=item.id) is None

    async def test_replay_de_outro_tenant_levanta(self, sessao_db) -> None:
        a = await criar_tenant(sessao_db, "d-c")
        b = await criar_tenant(sessao_db, "d-d")
        item = await svc.enfileirar(sessao_db, tenant_id=a.id, fila="f", payload={})
        await sessao_db.commit()
        with pytest.raises(svc.ErroDLQ, match="não encontrado"):
            await svc.preparar_replay(sessao_db, tenant_id=b.id, item_id=item.id)

    async def test_id_inexistente(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "d-e")
        with pytest.raises(svc.ErroDLQ):
            await svc.preparar_replay(sessao_db, tenant_id=tenant.id, item_id=uuid.uuid4())
