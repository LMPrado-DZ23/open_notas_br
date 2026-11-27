"""Worker assíncrono (ARQ).

Por que ARQ e não Celery: o projeto já é asyncio de ponta a ponta (FastAPI +
SQLAlchemy async + redis.asyncio). ARQ usa o mesmo event loop e a mesma conexão
Redis, sem broker extra nem processo pool separado. Celery traria pré-fork,
serialização própria e mais uma superfície de configuração sem ganho aqui.

Jobs:

- `ping` — verificação de que a fila é consumida.
- `heartbeat` — batimento a cada 30 s, usado pelo healthcheck do container para
  provar que o worker **processa**, não apenas que o processo está de pé.
- `entregar_webhooks` — retenta as entregas vencidas. O backoff real está no
  registro (`proxima_tentativa`); o cron só define a granularidade.
- `processar_lote` — processa um lote já criado.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configurar_logging

logger = logging.getLogger(__name__)

#: Chave de batimento. O healthcheck do worker lê esta chave.
CHAVE_HEARTBEAT = "notasbr:worker:heartbeat"
#: TTL do batimento. Precisa ser maior que o intervalo entre batimentos.
TTL_HEARTBEAT_SEGUNDOS = 120


async def ping(ctx: dict[str, Any]) -> str:
    """Job trivial, útil para verificar que a fila está sendo consumida."""
    logger.info("job_ping", extra={"job_id": ctx.get("job_id")})
    return "pong"


async def heartbeat(ctx: dict[str, Any]) -> None:
    """Registra que o worker está processando, com TTL no Redis."""
    redis = ctx["redis"]
    agora = datetime.now(UTC).isoformat()
    await redis.set(CHAVE_HEARTBEAT, agora, ex=TTL_HEARTBEAT_SEGUNDOS)
    logger.debug("worker_heartbeat", extra={"em": agora})


async def entregar_webhooks(ctx: dict[str, Any]) -> dict[str, int]:
    """Entrega as webhooks vencidas.

    Job de fila, e não `POST` dentro da requisição: endpoint do cliente lento não
    pode segurar a resposta da emissão.
    """
    from app.db.session import obter_sessionmaker_worker
    from app.webhooks.service import processar_pendentes

    async with obter_sessionmaker_worker()() as sessao:
        contagem = await processar_pendentes(sessao)
        await sessao.commit()
    logger.info("job_webhooks", extra={"contagem": contagem})
    return contagem


async def processar_lote(ctx: dict[str, Any], lote_id: str) -> str:
    """Processa um lote criado por `POST /v1/lotes` (status PENDENTE)."""
    import uuid

    from app.batches import service as lote_service
    from app.batches.csv import LinhaLote, LoteLido
    from app.core.config import get_settings as settings_local
    from app.db.models.ops import BatchJob
    from app.db.models.tenant import Tenant
    from app.db.session import obter_sessionmaker_worker
    from app.nfse.factory import montar_adapter

    configuracao = settings_local()
    # `None` aqui é deliberado: no caminho real quem monta o cliente é o serviço de emissão,
    # com o `AmbienteFiscal` do tenant e o certificado dele. Um cliente montado com `Settings`
    # caía sempre na SEFIN de homologação e sem mTLS (ver app/nfse/factory.py).
    adapter: Any = montar_adapter(configuracao)

    async with obter_sessionmaker_worker()() as sessao:
        job = await sessao.get(BatchJob, uuid.UUID(lote_id))
        if job is None:
            return f"lote {lote_id} não encontrado"
        tenant = await sessao.get(Tenant, job.tenant_id)
        if tenant is None:
            return f"tenant do lote {lote_id} não encontrado"

        # O relatório gravado na criação é a fonte das linhas: o CSV original NÃO
        # é persistido, porque é dado do cliente e não precisa ficar conosco.
        linhas = [
            LinhaLote(
                numero_linha=item.get("linha", 0),
                idempotency_key=item.get("idempotency_key") or "",
                erro=item.get("erro"),
            )
            for item in (job.relatorio or [])
        ]
        lote = LoteLido(linhas=linhas)
        await lote_service.processar(sessao, job, lote, tenant, adapter=adapter)
        await sessao.commit()
        sucesso, falhas = job.sucesso, job.falhas
    return f"lote {lote_id}: {sucesso} sucesso, {falhas} falha(s)"


async def ao_iniciar(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configurar_logging(settings.log_level, json_output=settings.log_json)
    logger.info("worker_iniciado", extra={"ambiente": settings.environment})


async def ao_encerrar(ctx: dict[str, Any]) -> None:
    logger.info("worker_encerrado")


class WorkerSettings:
    """Configuração consumida por `arq app.worker.main.WorkerSettings`."""

    functions: ClassVar[list[Any]] = [ping, entregar_webhooks, processar_lote]
    cron_jobs: ClassVar[list[Any]] = [
        # A cada 30 segundos: comprova processamento, não só processo vivo.
        cron(heartbeat, second={0, 30}, run_at_startup=True),
        # Webhook vencida é retentada a cada 15 s. O backoff real está no registro
        # (`proxima_tentativa`); esta frequência só define a granularidade.
        cron(entregar_webhooks, second=set(range(0, 60, 15)), run_at_startup=True),
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    on_startup = ao_iniciar
    on_shutdown = ao_encerrar
    keep_result = 3600
    max_tries = 3
    health_check_interval = 30
    # Evita que um job travado bloqueie a fila indefinidamente.
    job_timeout = 300
