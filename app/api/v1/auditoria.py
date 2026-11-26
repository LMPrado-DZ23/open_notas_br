"""Consulta do laudo de cálculo (auditoria fiscal).

Rota **de leitura** e restrita ao tenant da credencial. Não existe rota de escrita:
laudo se grava no fluxo de emissão, nunca por API — aceitar laudo do cliente
transformaria a prova em declaração.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import tenant_atual
from app.db.models.tenant import Tenant
from app.db.session import get_session
from app.tax import auditoria_service as svc

router = APIRouter(prefix="/tax/audit", tags=["auditoria"])


def _serializar(registro) -> dict:
    return {
        "id": str(registro.id),
        "trace_id": registro.trace_id,
        "versao_formato": registro.versao_formato,
        "hash_entrada": registro.hash_entrada,
        "hash_saida": registro.hash_saida,
        "hash_laudo": registro.hash_laudo,
        "data_emissao": registro.data_emissao.isoformat() if registro.data_emissao else None,
        "regras": registro.regras,
        "tabelas": registro.tabelas,
        "entrada": registro.entrada,
        "saida": registro.saida,
        "created_at": registro.created_at.isoformat(),
    }


@router.get("/{registro_id}")
async def obter_laudo(
    registro_id: uuid.UUID,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Devolve o laudo completo. Laudo de outro tenant responde 404, não 403."""
    registro = await svc.por_id(db, tenant_id=tenant.id, registro_id=registro_id)
    if registro is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="laudo não encontrado")
    return _serializar(registro)


@router.get("")
async def listar_por_trace(
    trace_id: str = Query(min_length=1, max_length=64),
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Todos os cálculos de um `trace_id`. Lista, porque o mesmo trace pode cobrir
    mais de um cálculo (produto e serviço na mesma operação)."""
    registros = await svc.por_trace(db, tenant_id=tenant.id, trace_id=trace_id)
    return {"itens": [_serializar(r) for r in registros], "total": len(registros)}


@router.get("/{registro_id}/integridade")
async def verificar_laudo(
    registro_id: uuid.UUID,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Recalcula os hashes do que está gravado.

    `integra` falso significa que o conteúdo foi alterado direto no banco: o laudo
    existe, mas não corresponde mais ao cálculo original.
    """
    registro = await svc.por_id(db, tenant_id=tenant.id, registro_id=registro_id)
    if registro is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="laudo não encontrado")
    return {
        "id": str(registro.id),
        "integra": await svc.verificar_integridade(registro),
        "hash_entrada_gravado": registro.hash_entrada,
        "hash_saida_gravado": registro.hash_saida,
    }
