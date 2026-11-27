"""Rotas de integração por parceiro.

Uma rota por parceiro, com o mesmo comportamento de emissão. O parceiro envia o
payload dele; o conector traduz; o serviço fiscal emite com a idempotência
derivada do `evento_id`.

Respostas:

- ``201`` nota autorizada (primeira vez do evento).
- ``200`` evento já processado — devolve a nota existente. Webhook repetido do
  parceiro é normal, não é erro, e não pode virar segunda nota.
- ``422`` payload inválido, com o campo que faltou.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import tenant_atual
from app.certificates.service import ErroDeCertificadoDeTenant
from app.core.config import Settings, get_settings
from app.db.models.enums import StatusFatura
from app.db.models.invoice import Invoice
from app.db.models.tenant import Tenant
from app.db.session import get_session
from app.integrations.base import ErroDeIntegracao, PedidoEmissao
from app.integrations.brizu.conector import ConectorBrizu
from app.integrations.dz23.conector import ConectorDz23
from app.nfse import servico as emissao_service
from app.nfse.adapter import SefinAdapter
from app.nfse.errors import ErroSefin
from app.nfse.factory import montar_adapter

HTTP_200 = 200
HTTP_201 = 201
HTTP_422 = 422

router = APIRouter(tags=["integracoes"])

CONECTORES: dict[str, Any] = {
    "dz23": ConectorDz23(),
    "brizu": ConectorBrizu(),
}


class EventoParceiroOut(BaseModel):
    """Resultado da integração."""

    parceiro: str
    evento_id: str
    idempotency_key: str
    status: str
    ja_existia: bool
    invoice_id: str
    chave: str | None = None


def _montar_adapter(settings: Settings) -> SefinAdapter | None:
    """Dublê quando configurado, `None` para o serviço montar o cliente real.

    Ver `app/nfse/factory.py`: montar o cliente aqui com `Settings` mandava a emissão
    para a SEFIN de **homologação** e sem certificado de cliente.
    """
    return montar_adapter(settings)


async def _processar(
    parceiro: str,
    payload: dict[str, Any],
    tenant: Tenant,
    db: AsyncSession,
    settings: Settings,
) -> tuple[EventoParceiroOut, int]:
    conector = CONECTORES[parceiro]
    try:
        pedido: PedidoEmissao = conector.interpretar(payload)
    except ErroDeIntegracao as exc:
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc

    existente = await db.execute(
        select(Invoice).where(
            Invoice.tenant_id == tenant.id,
            Invoice.idempotency_key == pedido.idempotency_key,
        )
    )
    anterior = existente.scalars().first()
    if anterior is not None and anterior.status == StatusFatura.AUTORIZADA:
        await db.commit()
        return (
            EventoParceiroOut(
                parceiro=parceiro,
                evento_id=str(payload.get("evento_id")),
                idempotency_key=pedido.idempotency_key,
                status=anterior.status.value,
                ja_existia=True,
                invoice_id=str(anterior.id),
                chave=None,
            ),
            HTTP_200,
        )

    invoice = anterior or Invoice(
        tenant_id=tenant.id,
        idempotency_key=pedido.idempotency_key,
        status=StatusFatura.PENDENTE,
        valor_servico=str(pedido.valor),
        descricao_servico=pedido.descricao,
        competencia=pedido.competencia,
        tomador_nome=pedido.tomador_nome,
        tomador_documento=pedido.tomador_documento,
        tomador_email=pedido.tomador_email,
        referencia_externa=pedido.referencia_externa,
        payload={"origem": pedido.parceiro, **pedido.origem_payload},
    )
    if anterior is None:
        db.add(invoice)
        await db.flush()

    # Erro de pré-requisito do tenant (sem config fiscal, sem certificado) precisa
    # chegar ao parceiro como 4xx com o motivo. Virar 500 faria o parceiro
    # retentar para sempre algo que só o dono do tenant resolve.
    try:
        documento = await emissao_service.emitir(
            db, tenant, invoice, adapter=_montar_adapter(settings)
        )
    except (
        emissao_service.ConfiguracaoFiscalAusente,
        emissao_service.CertificadoAusente,
    ) as exc:
        await db.rollback()
        raise HTTPException(
            status_code=HTTP_422,
            detail={"motivo": "tenant_sem_pre_requisito", "mensagem": str(exc)},
        ) from exc
    except ErroDeCertificadoDeTenant as exc:
        await db.rollback()
        raise HTTPException(
            status_code=HTTP_422,
            detail={"motivo": "certificado_invalido", "mensagem": str(exc)},
        ) from exc
    except ErroSefin as exc:
        await db.rollback()
        raise HTTPException(
            status_code=HTTP_422,
            detail={"motivo": exc.tipo.value, "mensagem": str(exc)},
        ) from exc
    await db.commit()

    return (
        EventoParceiroOut(
            parceiro=parceiro,
            evento_id=str(payload.get("evento_id")),
            idempotency_key=pedido.idempotency_key,
            status=invoice.status.value,
            ja_existia=False,
            invoice_id=str(invoice.id),
            chave=documento.chave,
        ),
        HTTP_201,
    )


@router.post(
    "/integracoes/dz23/vendas",
    response_model=EventoParceiroOut,
    status_code=HTTP_201,
    summary="DZ23: venda/fatura paga vira NFS-e",
    responses={
        200: {"description": "Evento já processado (idempotente)"},
        422: {"description": "Payload inválido"},
    },
)
async def dz23_venda(
    payload: dict[str, Any],
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    from fastapi import Response

    saida, codigo = await _processar("dz23", payload, tenant, db, settings)
    return Response(
        content=saida.model_dump_json(), status_code=codigo, media_type="application/json"
    )


@router.post(
    "/integracoes/brizu/atendimentos",
    response_model=EventoParceiroOut,
    status_code=HTTP_201,
    summary="Brizu: atendimento pago vira NFS-e",
    responses={
        200: {"description": "Evento já processado (idempotente)"},
        422: {"description": "Payload inválido"},
    },
)
async def brizu_atendimento(
    payload: dict[str, Any],
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    from fastapi import Response

    saida, codigo = await _processar("brizu", payload, tenant, db, settings)
    return Response(
        content=saida.model_dump_json(), status_code=codigo, media_type="application/json"
    )
