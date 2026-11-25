"""Entrega de webhooks com assinatura, retry e backoff exponencial.

Regras que o código garante:

- **A entrega é um registro persistido**, não um `POST` no meio da requisição. Se
  o processo morrer, a entrega continua pendente e é retomada.
- **Backoff exponencial** com teto: 10 s, 30 s, 2 min, 10 min, 30 min. Retentar
  agressivo em endpoint fora do ar queima cota e vira ruído.
- **Limite de tentativas.** Depois do limite a entrega fica `FALHOU` com o último
  erro — não desaparece, para o operador poder reprocessar.
- **2xx é sucesso**; qualquer outro status é falha, inclusive 3xx (o cliente HTTP
  não segue redirecionamento, para não entregar payload assinado a outro host).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import Cofre, aad_do_tenant
from app.db.models.enums import StatusWebhook
from app.db.models.ops import WebhookDelivery
from app.db.models.tenant import Tenant
from app.webhooks.assinatura import cabecalhos, gerar_segredo

logger = logging.getLogger(__name__)

#: Intervalos de retentativa, em segundos. Índice = tentativa já feita.
BACKOFF_SEGUNDOS: tuple[int, ...] = (10, 30, 120, 600, 1800)
MAX_TENTATIVAS = len(BACKOFF_SEGUNDOS)
TIMEOUT_ENTREGA_SEGUNDOS = 10.0


class ErroWebhook(Exception):
    """Falha ao configurar ou entregar webhook."""


def _agora() -> datetime:
    return datetime.now(UTC)


def _cofre() -> Cofre:
    """Cofre com a chave-mestra vigente.

    A chave vem de `Settings.master_key()`, que falha em produção se a variável
    não existir — nunca cai em chave padrão.
    """
    from app.core.config import get_settings

    return Cofre(get_settings().master_key())


def _aad(tenant_id: object) -> bytes:
    """Contexto de selagem do segredo de webhook.

    Composto com o do tenant (`tenant:<id>`) e acrescido do propósito. Sem o
    sufixo, um envelope de certificado A1 poderia ser trocado pelo do segredo de
    webhook no banco: os dois abririam no mesmo contexto.
    """
    return aad_do_tenant(tenant_id) + b":webhook"


def proxima_tentativa(tentativas: int, *, agora: datetime | None = None) -> datetime | None:
    """Quando retentar, ou ``None`` se esgotou."""
    if tentativas >= MAX_TENTATIVAS:
        return None
    atraso = BACKOFF_SEGUNDOS[tentativas]
    return (agora or _agora()) + timedelta(seconds=atraso)


async def configurar_endpoint(
    sessao: AsyncSession, tenant: Tenant, url: str, *, rotacionar: bool = False
) -> str | None:
    """Define a URL de webhook e, se necessário, gera o segredo.

    O segredo é **selado** com AES-256-GCM antes de tocar o banco e só é devolvido
    em claro nesta chamada — depois disso, nem a API o mostra de novo. Perder o
    segredo exige rotacionar, que é justamente o caminho oferecido.
    """
    if not url.startswith(("https://", "http://")):
        raise ErroWebhook("URL de webhook deve começar com http:// ou https://")

    cofre = _cofre()
    tenant.webhook_url = url

    segredo_novo: str | None = None
    if tenant.webhook_secret_selado is None or rotacionar:
        segredo_novo = gerar_segredo()
        tenant.webhook_secret_selado = cofre.selar(
            segredo_novo.encode("utf-8"), aad=_aad(tenant.id)
        )
    await sessao.flush()
    return segredo_novo


def obter_segredo(tenant: Tenant) -> bytes | None:
    """Segredo em claro, apenas em memória, para assinar a entrega."""
    if tenant.webhook_secret_selado is None:
        return None
    return _cofre().abrir(tenant.webhook_secret_selado, aad=_aad(tenant.id))


async def enfileirar(
    sessao: AsyncSession,
    tenant: Tenant,
    *,
    tipo_evento: str,
    payload: dict[str, Any],
    url: str | None = None,
) -> WebhookDelivery | None:
    """Registra uma entrega pendente. Sem URL configurada, não cria nada.

    Devolver ``None`` em vez de levantar é deliberado: a emissão da nota não pode
    falhar porque o cliente não configurou webhook.
    """
    destino = url or tenant.webhook_url
    if not destino:
        logger.info("webhook_sem_endpoint", extra={"tenant_id": str(tenant.id)})
        return None

    entrega = WebhookDelivery(
        tenant_id=tenant.id,
        tipo_evento=tipo_evento,
        url_destino=destino,
        payload=payload,
        status=StatusWebhook.PENDENTE,
        tentativas=0,
        proxima_tentativa=_agora(),
    )
    sessao.add(entrega)
    await sessao.flush()
    return entrega


async def entregar(
    sessao: AsyncSession,
    entrega: WebhookDelivery,
    *,
    cliente: httpx.AsyncClient | None = None,
) -> WebhookDelivery:
    """Tenta entregar uma vez e atualiza o registro."""
    resultado = await sessao.execute(select(Tenant).where(Tenant.id == entrega.tenant_id))
    tenant = resultado.scalar_one_or_none()
    if tenant is None:  # pragma: no cover - integridade referencial impede
        entrega.status = StatusWebhook.FALHOU
        entrega.ultimo_erro = "tenant da entrega não existe"
        await sessao.flush()
        return entrega

    try:
        segredo = obter_segredo(tenant)
    except Exception as exc:
        # Segredo selado com outra chave-mestra (ex.: chave trocada, backup
        # restaurado em outro ambiente). Não há como recuperar: o caminho é
        # rotacionar. Marcar como falha evita retentativa infinita inútil.
        entrega.status = StatusWebhook.FALHOU
        entrega.ultimo_erro = (
            f"segredo de webhook ilegível ({type(exc).__name__}): "
            "rotacione o segredo em POST /v1/me/webhook"
        )
        await sessao.flush()
        logger.error("webhook_segredo_ilegivel", extra={"entrega_id": str(entrega.id)})
        return entrega

    if segredo is None:
        entrega.status = StatusWebhook.FALHOU
        entrega.ultimo_erro = "tenant sem segredo de webhook configurado"
        await sessao.flush()
        return entrega

    import json

    corpo = json.dumps(entrega.payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    cabecalho = cabecalhos(segredo, corpo, evento=entrega.tipo_evento, entrega_id=str(entrega.id))
    entrega.assinatura = cabecalho["X-Notasbr-Signature"].split("v1=")[-1]

    proprio = cliente is None
    http = cliente or httpx.AsyncClient(timeout=TIMEOUT_ENTREGA_SEGUNDOS, follow_redirects=False)
    try:
        resposta = await http.post(entrega.url_destino, content=corpo, headers=cabecalho)
        entrega.codigo_http = resposta.status_code
        if 200 <= resposta.status_code < 300:
            entrega.status = StatusWebhook.ENTREGUE
            entrega.entregue_em = _agora()
            entrega.ultimo_erro = None
            entrega.proxima_tentativa = None
        else:
            _registrar_falha(entrega, f"HTTP {resposta.status_code}")
    except httpx.HTTPError as exc:
        _registrar_falha(entrega, f"falha de rede: {type(exc).__name__}")
    finally:
        if proprio:
            await http.aclose()

    await sessao.flush()
    logger.info(
        "webhook_entrega",
        extra={
            "entrega_id": str(entrega.id),
            "status": entrega.status.value,
            "tentativas": entrega.tentativas,
            "codigo_http": entrega.codigo_http,
        },
    )
    return entrega


def _registrar_falha(entrega: WebhookDelivery, motivo: str) -> None:
    entrega.tentativas += 1
    entrega.ultimo_erro = motivo[:500]
    seguinte = proxima_tentativa(entrega.tentativas)
    if seguinte is None:
        entrega.status = StatusWebhook.FALHOU
        entrega.proxima_tentativa = None
    else:
        entrega.status = StatusWebhook.PENDENTE
        entrega.proxima_tentativa = seguinte


async def pendentes_para_entrega(
    sessao: AsyncSession, *, limite: int = 50, agora: datetime | None = None
) -> list[WebhookDelivery]:
    """Entregas vencidas, prontas para nova tentativa."""
    momento = agora or _agora()
    resultado = await sessao.execute(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.status == StatusWebhook.PENDENTE,
            WebhookDelivery.proxima_tentativa.is_not(None),
            WebhookDelivery.proxima_tentativa <= momento,
        )
        .order_by(WebhookDelivery.proxima_tentativa)
        .limit(limite)
    )
    return list(resultado.scalars().all())


async def processar_pendentes(
    sessao: AsyncSession, *, limite: int = 50, cliente: httpx.AsyncClient | None = None
) -> dict[str, int]:
    """Entrega tudo que está vencido. Devolve contagem por desfecho."""
    entregas = await pendentes_para_entrega(sessao, limite=limite)
    contagem = {"entregues": 0, "pendentes": 0, "falhas": 0}
    for entrega in entregas:
        try:
            await entregar(sessao, entrega, cliente=cliente)
        except Exception as exc:
            # Isolamento por entrega: uma falha inesperada não pode travar a fila
            # de todo mundo. O registro fica com o motivo e o laço continua.
            logger.exception("webhook_entrega_inesperada", extra={"entrega_id": str(entrega.id)})
            entrega.status = StatusWebhook.FALHOU
            entrega.ultimo_erro = f"erro inesperado: {type(exc).__name__}: {str(exc)[:300]}"
            await sessao.flush()
        if entrega.status == StatusWebhook.ENTREGUE:
            contagem["entregues"] += 1
        elif entrega.status == StatusWebhook.FALHOU:
            contagem["falhas"] += 1
        else:
            contagem["pendentes"] += 1
    return contagem
