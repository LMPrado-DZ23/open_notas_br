"""DLQ: enfileirar, listar e reprocessar com isolamento de tenant."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.dlq import ItemDLQ, StatusDLQ


class ErroDLQ(Exception):
    """Item inexistente, já processado, ou de outro tenant."""


async def enfileirar(
    sessao: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    fila: str,
    payload: dict[str, Any],
    erro: str | None = None,
    trace_id: str | None = None,
    tentativas: int = 0,
) -> ItemDLQ:
    """Guarda o trabalho que falhou. Não faz commit: quem chama controla a transação."""
    item = ItemDLQ(
        tenant_id=tenant_id,
        fila=fila,
        payload=payload,
        erro=(erro[:4000] if erro else None),
        trace_id=trace_id,
        tentativas=tentativas,
    )
    sessao.add(item)
    await sessao.flush()
    return item


async def listar(
    sessao: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    status: StatusDLQ | None = StatusDLQ.PENDENTE,
    fila: str | None = None,
    limite: int = 50,
) -> list[ItemDLQ]:
    filtros = [ItemDLQ.tenant_id == tenant_id]
    if status is not None:
        filtros.append(ItemDLQ.status == status)
    if fila:
        filtros.append(ItemDLQ.fila == fila)
    consulta = select(ItemDLQ).where(*filtros).order_by(ItemDLQ.created_at).limit(limite)
    return list((await sessao.execute(consulta)).scalars().all())


async def por_id(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> ItemDLQ | None:
    consulta = select(ItemDLQ).where(ItemDLQ.id == item_id, ItemDLQ.tenant_id == tenant_id)
    return (await sessao.execute(consulta)).scalar_one_or_none()


async def preparar_replay(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> ItemDLQ:
    """Valida e marca o item para replay, devolvendo-o.

    **Não** executa a tarefa: quem reexecuta é o worker, que conhece a fila. Aqui a
    responsabilidade é decidir se o replay é legítimo.

    Recusa item já reprocessado: replay duplo reenviaria a mesma nota. É a falha mais
    cara possível neste sistema.
    """
    item = await por_id(sessao, tenant_id=tenant_id, item_id=item_id)
    if item is None:
        raise ErroDLQ("item de DLQ não encontrado")
    if item.status is StatusDLQ.REPROCESSADO:
        raise ErroDLQ("item já foi reprocessado; replay duplo reenviaria a nota")
    if item.status is StatusDLQ.DESCARTADO:
        raise ErroDLQ("item foi descartado e não pode ser reprocessado")

    item.status = StatusDLQ.REPROCESSADO
    item.tentativas += 1
    item.reprocessado_em = datetime.now(UTC)
    await sessao.flush()
    return item


async def marcar_replay_falhou(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID, erro: str
) -> ItemDLQ:
    """Desfaz a marca de reprocessado quando o replay falha.

    Sem isto, um replay que falhou ficaria marcado como bem-sucedido e o trabalho se
    perderia em silêncio.
    """
    item = await por_id(sessao, tenant_id=tenant_id, item_id=item_id)
    if item is None:
        raise ErroDLQ("item de DLQ não encontrado")
    item.status = StatusDLQ.PENDENTE
    item.erro = erro[:4000]
    await sessao.flush()
    return item


async def descartar(sessao: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID) -> ItemDLQ:
    item = await por_id(sessao, tenant_id=tenant_id, item_id=item_id)
    if item is None:
        raise ErroDLQ("item de DLQ não encontrado")
    item.status = StatusDLQ.DESCARTADO
    await sessao.flush()
    return item
