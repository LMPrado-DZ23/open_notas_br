"""Rotas de lote e de configuração de webhook.

Lote tem dois modos, por decisão explícita:

- **assíncrono** (padrão): cria o registro e enfileira no worker. É o modo para
  arquivo grande.
- **`processar_agora=true`**: processa na própria requisição e devolve o relatório.
  Existe porque operar lote sem worker de pé precisa ser possível, e porque teste
  de integração não deve depender de processo externo.

Webhook: o segredo só aparece em claro na resposta que o gera. Depois disso, nem
`GET` o mostra — perder exige rotacionar.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import tenant_atual
from app.batches import service as lote_service
from app.batches.csv import CsvInvalido
from app.core.config import Settings, get_settings
from app.db.models.ops import BatchJob, WebhookDelivery
from app.db.models.tenant import Tenant
from app.db.session import get_session
from app.nfse.adapter import SefinAdapter
from app.nfse.factory import montar_adapter
from app.webhooks import service as webhook_service
from app.webhooks.service import ErroWebhook

HTTP_404 = 404
HTTP_413 = 413
HTTP_422 = 422
TAMANHO_MAXIMO_CSV = 5 * 1024 * 1024

router = APIRouter(tags=["lotes"])


class LoteOut(BaseModel):
    id: uuid.UUID
    status: str
    nome_arquivo: str | None
    total_linhas: int
    processadas: int
    sucesso: int
    falhas: int
    erro: str | None = None


class LoteDetalheOut(LoteOut):
    relatorio: list[dict] | None = None


class WebhookConfigIn(BaseModel):
    url: str = Field(..., min_length=10, max_length=500)
    rotacionar_segredo: bool = False


class WebhookConfigOut(BaseModel):
    url: str | None
    tem_segredo: bool
    #: Só vem preenchido quando o segredo é criado ou rotacionado.
    segredo: str | None = None
    aviso: str | None = None


class EntregaOut(BaseModel):
    id: uuid.UUID
    tipo_evento: str
    url_destino: str
    status: str
    tentativas: int
    codigo_http: int | None = None
    ultimo_erro: str | None = None


def _lote(job: BatchJob) -> LoteOut:
    return LoteOut(
        id=job.id,
        status=job.status.value,
        nome_arquivo=job.nome_arquivo,
        total_linhas=job.total_linhas,
        processadas=job.processadas,
        sucesso=job.sucesso,
        falhas=job.falhas,
        erro=job.erro,
    )


def _montar_adapter(settings: Settings) -> SefinAdapter | None:
    """Dublê quando configurado, `None` para o serviço montar o cliente real.

    Ver `app/nfse/factory.py`: montar o cliente aqui com `Settings` mandava a emissão
    para a SEFIN de **homologação** e sem certificado de cliente.
    """
    return montar_adapter(settings)


@router.post(
    "/lotes",
    response_model=LoteDetalheOut,
    summary="Importa CSV de emissões e cria o lote",
    responses={
        413: {"description": "Arquivo maior que 5 MB"},
        422: {"description": "CSV inválido (sem cabeçalho ou sem linhas)"},
    },
)
async def criar_lote(
    arquivo: Annotated[UploadFile, File(description="CSV com cabeçalho")],
    processar_agora: bool = Query(
        default=False, description="Processa na requisição em vez de enfileirar"
    ),
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> LoteDetalheOut:
    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAXIMO_CSV:
        raise HTTPException(
            status_code=HTTP_413,
            detail=f"arquivo acima de {TAMANHO_MAXIMO_CSV // (1024 * 1024)} MB",
        )

    try:
        job, lote = await lote_service.criar(
            db, tenant, nome_arquivo=arquivo.filename or "lote.csv", conteudo=conteudo
        )
    except CsvInvalido as exc:
        await db.rollback()
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc

    if processar_agora:
        job = await lote_service.processar(db, job, lote, tenant, adapter=_montar_adapter(settings))

    await db.commit()
    await db.refresh(job)
    return LoteDetalheOut(**_lote(job).model_dump(), relatorio=job.relatorio)


@router.get("/lotes", response_model=list[LoteOut], summary="Lista os lotes do tenant")
async def listar_lotes(
    limite: int = Query(default=50, ge=1, le=200),
    deslocamento: int = Query(default=0, ge=0),
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> list[LoteOut]:
    jobs = await lote_service.listar(db, tenant.id, limite=limite, deslocamento=deslocamento)
    return [_lote(j) for j in jobs]


@router.get(
    "/lotes/{lote_id}",
    response_model=LoteDetalheOut,
    summary="Detalhe do lote com relatório linha a linha",
)
async def detalhar_lote(
    lote_id: uuid.UUID,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> LoteDetalheOut:
    try:
        job = await lote_service.por_id(db, tenant.id, lote_id)
    except lote_service.ErroDeLote as exc:
        raise HTTPException(status_code=HTTP_404, detail=str(exc)) from exc
    return LoteDetalheOut(**_lote(job).model_dump(), relatorio=job.relatorio)


@router.post(
    "/me/webhook",
    response_model=WebhookConfigOut,
    summary="Configura a URL de webhook e devolve o segredo uma única vez",
)
async def configurar_webhook(
    dados: WebhookConfigIn,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> WebhookConfigOut:
    try:
        segredo = await webhook_service.configurar_endpoint(
            db, tenant, dados.url, rotacionar=dados.rotacionar_segredo
        )
        await db.commit()
    except ErroWebhook as exc:
        await db.rollback()
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc

    return WebhookConfigOut(
        url=tenant.webhook_url,
        tem_segredo=tenant.webhook_secret_selado is not None,
        segredo=segredo,
        aviso=(
            "guarde este segredo agora: ele não será exibido novamente"
            if segredo
            else "segredo já existia; use rotacionar_segredo=true para gerar outro"
        ),
    )


@router.get(
    "/me/webhook",
    response_model=WebhookConfigOut,
    summary="Mostra a URL configurada (sem expor o segredo)",
)
async def ver_webhook(tenant: Tenant = Depends(tenant_atual)) -> WebhookConfigOut:
    return WebhookConfigOut(
        url=tenant.webhook_url,
        tem_segredo=tenant.webhook_secret_selado is not None,
        segredo=None,
        aviso="o segredo não é recuperável; rotacione se perdeu",
    )


@router.get(
    "/me/webhook/entregas",
    response_model=list[EntregaOut],
    summary="Lista as entregas de webhook do tenant",
)
async def listar_entregas(
    limite: int = Query(default=50, ge=1, le=200),
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> list[EntregaOut]:
    resultado = await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.tenant_id == tenant.id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limite)
    )
    return [
        EntregaOut(
            id=e.id,
            tipo_evento=e.tipo_evento,
            url_destino=e.url_destino,
            status=e.status.value,
            tentativas=e.tentativas,
            codigo_http=e.codigo_http,
            ultimo_erro=e.ultimo_erro,
        )
        for e in resultado.scalars().all()
    ]
