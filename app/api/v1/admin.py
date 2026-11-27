"""Operações de plataforma (admin): replay de DLQ.

ADR 0001, opção A. **Desligado por padrão**: `admin_habilitado=False` faz a rota
responder **404** (não 403) — quem não deve saber que ela existe não descobre pelo
código de erro.

A comparação da chave usa `secrets.compare_digest`: comparação com `==` vaza o tamanho
do prefixo correto pelo tempo de resposta.

`X-Admin-Key` é um header separado da API key de tenant, e **não** substitui a de tenant:
uma chave de admin nunca deve poder emitir nota, e uma de tenant nunca deve reprocessar
fila morta.
"""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.worker import dlq as dlq_service

router = APIRouter(prefix="/admin", tags=["admin"])


async def exigir_admin(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    settings: Settings = Depends(get_settings),
) -> None:
    """Autoriza a operação de plataforma.

    404 quando o admin não está habilitado: a rota não deve existir para quem não a
    conhece. 401 quando a chave está errada.
    """
    if not settings.admin_habilitado or not settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if not x_admin_key or not secrets.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="chave de admin inválida",
            headers={"WWW-Authenticate": "X-Admin-Key"},
        )


@router.post("/dlq/{item_id}/replay", dependencies=[Depends(exigir_admin)])
async def reprocessar_dlq(
    item_id: uuid.UUID,
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Marca o item para replay.

    `tenant_id` é **explícito** e obrigatório: operação de admin atravessa tenants por
    natureza, e deixar implícito esconderia qual tenant está sendo afetado. O serviço
    continua exigindo o tenant certo, então o isolamento não é burlado — ele é declarado.

    Não executa a tarefa: quem reexecuta é o worker. Aqui se decide se o replay é
    legítimo (o serviço recusa replay duplo e item descartado).
    """
    try:
        item = await dlq_service.preparar_replay(db, tenant_id=tenant_id, item_id=item_id)
    except dlq_service.ErroDLQ as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    return {
        "id": str(item.id),
        "fila": item.fila,
        "status": str(item.status),
        "tentativas": item.tentativas,
    }


@router.post(
    "/tenants/{tenant_id}/revogar-chave",
    status_code=204,
    dependencies=[Depends(exigir_admin)],
    summary="Revoga a API key de um tenant (operação de plataforma)",
)
async def revogar_chave_do_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
) -> None:
    """Mata a credencial sem emitir outra (adendo §5).

    Quem usa: operador diante de vazamento ou desligamento. O tenant fica **sem acesso** até que
    outra chave seja emitida — comportamento correto para credencial comprometida, e diferente de
    rotação, que já devolve a nova ao dono.

    `404` quando o admin não está habilitado (ADR 0001: quem não deve saber que a rota existe não
    descobre pelo código de erro).
    """
    from app.tenants import service as tenant_service

    try:
        await tenant_service.revogar_chave(db, tenant_id)
        await db.commit()
    except tenant_service.ErroDeTenant as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail="tenant não encontrado") from exc
