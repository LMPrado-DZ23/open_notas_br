"""Rotas de emissão de NFS-e.

`POST /v1/emissoes` é síncrono de propósito nesta fase: o parceiro recebe a chave
ou a rejeição na mesma chamada. A Fase 5 acrescenta o caminho assíncrono por fila
para lote; a semântica de idempotência é a mesma e já está implementada.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import tenant_atual
from app.core.config import Settings, get_settings
from app.db.models.enums import StatusFatura, TipoDocumento
from app.db.models.invoice import FiscalDocument, Invoice
from app.db.models.tenant import Tenant
from app.db.session import get_session
from app.nfse import servico as emissao_service
from app.nfse.adapter import SefinMockAdapter
from app.nfse.errors import ErroSefin
from app.nfse.schemas import DocumentoOut, EmissaoDetalheOut, EmissaoIn, EmissaoOut
from app.nfse.servico import (
    CertificadoAusente,
    ConfiguracaoFiscalAusente,
    ErroDeEmissao,
)

HTTP_409 = 409
HTTP_422 = 422
HTTP_502 = 502

router = APIRouter(tags=["emissao"])


def _documento_out(documento: FiscalDocument | None) -> DocumentoOut | None:
    if documento is None:
        return None
    return DocumentoOut(
        id=documento.id,
        tipo_documento=documento.tipo_documento.value,
        ambiente=documento.ambiente.value,
        chave=documento.chave,
        emitido_em=documento.emitido_em,
        tem_xml_autorizado=bool(documento.xml_autorizado),
    )


def _emissao_out(
    invoice: Invoice, documento: FiscalDocument | None, *, ja_existia: bool
) -> EmissaoOut:
    return EmissaoOut(
        invoice_id=invoice.id,
        status=invoice.status,
        valor=invoice.valor_servico,
        idempotency_key=invoice.idempotency_key,
        documento=_documento_out(documento),
        chave=documento.chave if documento else None,
        erro=invoice.erro,
        ja_existia=ja_existia,
    )


async def _buscar_por_idempotencia(
    db: AsyncSession, tenant_id: uuid.UUID, chave: str
) -> Invoice | None:
    resultado = await db.execute(
        select(Invoice).where(Invoice.tenant_id == tenant_id, Invoice.idempotency_key == chave)
    )
    return resultado.scalar_one_or_none()


async def _documento_da_fatura(db: AsyncSession, invoice: Invoice) -> FiscalDocument | None:
    resultado = await db.execute(
        select(FiscalDocument)
        .where(
            FiscalDocument.tenant_id == invoice.tenant_id, FiscalDocument.invoice_id == invoice.id
        )
        .order_by(FiscalDocument.created_at.desc())
    )
    return resultado.scalars().first()


@router.post(
    "/emissoes",
    response_model=EmissaoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Emite a NFS-e de um serviço (idempotente por idempotency_key)",
    responses={
        200: {"description": "A idempotency_key já havia sido processada"},
        422: {"description": "Configuração fiscal ou certificado ausente"},
        502: {"description": "A SEFIN recusou ou está indisponível"},
    },
)
async def emitir(
    dados: EmissaoIn,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> EmissaoOut:
    existente = await _buscar_por_idempotencia(db, tenant.id, dados.idempotency_key)
    if existente is not None:
        documento = await _documento_da_fatura(db, existente)
        if existente.status is StatusFatura.AUTORIZADA and documento is not None:
            corpo = _emissao_out(existente, documento, ja_existia=True)
            return JSONResponse(  # type: ignore[return-value]
                status_code=200, content=corpo.model_dump(mode="json")
            )
        # Fatura existe mas não está autorizada: reprocessar seria duplicar
        # tentativa sem o parceiro saber. Devolve o estado atual.
        return _emissao_out(existente, documento, ja_existia=True)

    invoice = Invoice(
        tenant_id=tenant.id,
        idempotency_key=dados.idempotency_key,
        status=StatusFatura.PENDENTE,
        tipo_documento=TipoDocumento.NFSE,
        origem=dados.origem,
        ambiente=dados.ambiente,
        valor_servico=dados.valor,
        descricao_servico=dados.descricao,
        competencia=dados.competencia,
        tomador_documento=dados.tomador_documento,
        tomador_nome=dados.tomador_nome,
        tomador_email=str(dados.tomador_email) if dados.tomador_email else None,
        referencia_externa=dados.referencia_externa,
        payload=dados.model_dump(mode="json"),
    )
    db.add(invoice)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existente = await _buscar_por_idempotencia(db, tenant.id, dados.idempotency_key)
        if existente is None:
            raise HTTPException(
                status_code=HTTP_409, detail="conflito de idempotência ao criar a fatura"
            ) from None
        return _emissao_out(existente, await _documento_da_fatura(db, existente), ja_existia=True)

    adaptador = SefinMockAdapter(dados.ambiente) if settings.nfse_adapter == "mock" else None

    try:
        documento = await emissao_service.emitir(
            db, tenant, invoice, adapter=adaptador, settings=settings
        )
        await db.commit()
    except (ConfiguracaoFiscalAusente, CertificadoAusente, ErroDeEmissao) as exc:
        await db.commit()  # preserva o evento de erro registrado
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc
    except ErroSefin as exc:
        await db.commit()  # preserva status e evento de rejeição
        raise HTTPException(status_code=HTTP_502, detail=exc.as_dict()) from exc

    await db.refresh(invoice)
    await db.refresh(documento)
    return _emissao_out(invoice, documento, ja_existia=False)


@router.get(
    "/emissoes/{invoice_id}",
    response_model=EmissaoDetalheOut,
    summary="Consulta uma emissão, com o XML autorizado",
)
async def consultar_emissao(
    invoice_id: uuid.UUID,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> EmissaoDetalheOut:
    resultado = await db.execute(
        select(Invoice).where(Invoice.tenant_id == tenant.id, Invoice.id == invoice_id)
    )
    invoice = resultado.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=404, detail="emissão não encontrada")

    documento = await _documento_da_fatura(db, invoice)
    base = _emissao_out(invoice, documento, ja_existia=False)
    return EmissaoDetalheOut(
        **base.model_dump(),
        xml_autorizado=documento.xml_autorizado if documento else None,
    )


@router.get(
    "/emissoes",
    response_model=list[EmissaoOut],
    summary="Lista as emissões do tenant",
)
async def listar_emissoes(
    limite: int = Query(default=50, ge=1, le=200),
    deslocamento: int = Query(default=0, ge=0),
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> list[EmissaoOut]:
    resultado = await db.execute(
        select(Invoice)
        .where(Invoice.tenant_id == tenant.id)
        .order_by(Invoice.created_at.desc())
        .limit(limite)
        .offset(deslocamento)
    )
    saida: list[EmissaoOut] = []
    for invoice in resultado.scalars().all():
        saida.append(
            _emissao_out(invoice, await _documento_da_fatura(db, invoice), ja_existia=False)
        )
    return saida
