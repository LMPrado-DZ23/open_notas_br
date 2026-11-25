"""Rotas de apuração e guias.

Apuração é consolidação do que foi autorizado; guia é o documento de pagamento.
Separar as duas é deliberado: consolidar pode ser refeito a qualquer momento
(idempotente por tenant+competência+provedor), enquanto gerar guia produz um
número que o contribuinte vai pagar.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import tenant_atual
from app.assessment import service
from app.assessment.providers import ErroDeGuia
from app.assessment.schemas import (
    ApuracaoDetalheOut,
    ApuracaoIn,
    ApuracaoOut,
    GuiaOut,
)
from app.assessment.service import CompetenciaInvalida, ErroDeApuracao
from app.db.models.tenant import Tenant
from app.db.session import get_session

HTTP_404 = 404
HTTP_422 = 422

router = APIRouter(tags=["apuracao"])


def _saida(apuracao) -> ApuracaoOut:
    return ApuracaoOut(
        id=apuracao.id,
        competencia=apuracao.competencia,
        provedor=apuracao.provedor,
        status=apuracao.status,
        total_servicos=str(Decimal(apuracao.total_servicos).quantize(Decimal("0.01"))),
        total_iss=str(Decimal(apuracao.total_iss).quantize(Decimal("0.01"))),
        total_tributos=str(Decimal(apuracao.total_tributos).quantize(Decimal("0.01"))),
        quantidade_documentos=apuracao.quantidade_documentos,
        guia_numero=apuracao.guia_numero,
        vencimento=apuracao.vencimento,
        linha_digitavel=apuracao.linha_digitavel,
        erro=apuracao.erro,
        created_at=apuracao.created_at,
        updated_at=apuracao.updated_at,
    )


@router.post(
    "/apuracoes",
    response_model=ApuracaoOut,
    summary="Consolida a competência (só documentos autorizados)",
    responses={422: {"description": "Competência inválida"}},
)
async def consolidar(
    dados: ApuracaoIn,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> ApuracaoOut:
    try:
        apuracao = await service.consolidar(
            db,
            tenant.id,
            dados.competencia,
            provedor=dados.provedor,
            ambiente=dados.ambiente,
        )
        await db.commit()
    except CompetenciaInvalida as exc:
        await db.rollback()
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc

    await db.refresh(apuracao)
    return _saida(apuracao)


@router.get(
    "/apuracoes",
    response_model=list[ApuracaoOut],
    summary="Lista as apurações do tenant",
)
async def listar(
    limite: int = Query(default=50, ge=1, le=200),
    deslocamento: int = Query(default=0, ge=0),
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> list[ApuracaoOut]:
    apuracoes = await service.listar(db, tenant.id, limite=limite, deslocamento=deslocamento)
    return [_saida(a) for a in apuracoes]


@router.get(
    "/apuracoes/{apuracao_id}",
    response_model=ApuracaoDetalheOut,
    summary="Detalhe da apuração, com avisos e alíquota usada",
)
async def detalhar(
    apuracao_id: uuid.UUID,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> ApuracaoDetalheOut:
    try:
        apuracao = await service.por_id(db, tenant.id, apuracao_id)
    except ErroDeApuracao as exc:
        raise HTTPException(status_code=HTTP_404, detail=str(exc)) from exc

    base = _saida(apuracao)
    return ApuracaoDetalheOut(**base.model_dump(), payload=apuracao.payload)


@router.post(
    "/apuracoes/{apuracao_id}/guia",
    response_model=GuiaOut,
    summary="Gera a guia da apuração com o provedor configurado",
    responses={422: {"description": "Provedor não conseguiu gerar (ex.: municipal sem layout)"}},
)
async def gerar_guia(
    apuracao_id: uuid.UUID,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> GuiaOut:
    try:
        apuracao = await service.por_id(db, tenant.id, apuracao_id)
    except ErroDeApuracao as exc:
        raise HTTPException(status_code=HTTP_404, detail=str(exc)) from exc

    try:
        guia = await service.gerar_guia(db, apuracao)
        await db.commit()
    except ErroDeGuia as exc:
        await db.commit()  # preserva status FALHOU e o motivo
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc

    return GuiaOut(**guia.to_dict())
