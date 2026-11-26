"""Emissão de CT-e e MDF-e: gera, assina com o certificado do tenant e devolve o XML.

**Isto não transmite.** Devolve o XML assinado e validado contra o schema oficial; o envio ao
autorizador depende de credenciamento e não é feito aqui. A rota é honesta quanto a isso: o
`summary` diz "gera e assina", não "emite".

O tenant vem da API key (`tenant_atual`). Não há `tenant_id` no corpo — aceitá-lo permitiria
assinar em nome de outro CNPJ.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, tenant_atual
from app.certificates import service as certificados
from app.core.config import Settings, get_settings
from app.cte import ErroCTe
from app.cte.gerador import gerar_assinado as gerar_cte
from app.cte.schemas import CTeIn
from app.db.models.tenant import Tenant
from app.mdfe import ErroMDFe
from app.mdfe.gerador import gerar_assinado as gerar_mdfe
from app.mdfe.schemas import MDFeIn

logger = logging.getLogger(__name__)

HTTP_422 = 422
router = APIRouter(prefix="/transportes", tags=["transporte"])

#: O XML assinado é a resposta; o cliente decide se transmite.
MEDIA_XML = "application/xml"


async def _certificado_do_tenant(sessao: AsyncSession, tenant: Tenant, conf: Settings):
    """Carrega o A1 ativo do tenant ou recusa com mensagem acionável.

    Sem certificado não há assinatura, e sem assinatura o CT-e/MDF-e é inválido pelo schema —
    então a recusa é 422 com o endpoint que resolve, não 500.
    """
    registro = await certificados.ativo(sessao, tenant.id)
    if registro is None:
        raise HTTPException(
            status_code=HTTP_422,
            detail=(
                "nenhum certificado A1 ativo para este tenant. "
                "Envie o .pfx em POST /v1/me/certificados."
            ),
        )
    return certificados.abrir_em_memoria(registro, settings=conf)


@router.post(
    "/cte",
    summary="Gera e assina um CT-e (não transmite)",
    response_class=Response,
    responses={
        200: {"content": {MEDIA_XML: {}}, "description": "XML do CT-e assinado e validado"},
        HTTP_422: {
            "description": "Dados inválidos, certificado ausente ou XML recusado pelo schema"
        },
    },
)
async def gerar_cte_assinado(
    payload: CTeIn,
    tenant: Annotated[Tenant, Depends(tenant_atual)],
    sessao: Annotated[AsyncSession, Depends(get_session)],
    conf: Annotated[Settings, Depends(get_settings)],
) -> Response:
    certificado = await _certificado_do_tenant(sessao, tenant, conf)
    try:
        xml = gerar_cte(payload.para_dominio(), certificado)
    except ErroCTe as exc:
        # O schema recusou: é erro do cliente (dados), não do servidor.
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc

    logger.info(
        "CT-e gerado e assinado",
        extra={"tenant_id": str(tenant.id), "chave": payload.chave},
    )
    return Response(content=xml, media_type=MEDIA_XML)


@router.post(
    "/mdfe",
    summary="Gera e assina um MDF-e (não transmite)",
    response_class=Response,
    responses={
        200: {"content": {MEDIA_XML: {}}, "description": "XML do MDF-e assinado e validado"},
        HTTP_422: {
            "description": "Dados inválidos, certificado ausente ou XML recusado pelo schema"
        },
    },
)
async def gerar_mdfe_assinado(
    payload: MDFeIn,
    tenant: Annotated[Tenant, Depends(tenant_atual)],
    sessao: Annotated[AsyncSession, Depends(get_session)],
    conf: Annotated[Settings, Depends(get_settings)],
) -> Response:
    certificado = await _certificado_do_tenant(sessao, tenant, conf)
    try:
        xml = gerar_mdfe(payload.para_dominio(), certificado)
    except ErroMDFe as exc:
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc

    logger.info(
        "MDF-e gerado e assinado",
        extra={"tenant_id": str(tenant.id), "chave": payload.chave},
    )
    return Response(content=xml, media_type=MEDIA_XML)
