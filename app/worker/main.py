"""Worker assíncrono (ARQ).

Por que ARQ e não Celery: o projeto já é asyncio de ponta a ponta (FastAPI +
SQLAlchemy async + redis.asyncio). ARQ usa o mesmo event loop e a mesma conexão
Redis, sem broker extra nem processo pool separado. Celery traria pré-fork,
serialização própria e mais uma superfície de configuração sem ganho aqui.

Na Fase 1 o worker entrega o que é verificável: um job `ping` e um batimento
(`heartbeat`) a cada 30 s, que o healthcheck do container usa para provar que o
worker está realmente processando e não apenas com o processo de pé. As tarefas
de emissão, lote e webhook entram nas Fases 5.
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


async def ao_iniciar(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configurar_logging(settings.log_level, json_output=settings.log_json)
    logger.info("worker_iniciado", extra={"ambiente": settings.environment})


async def ao_encerrar(ctx: dict[str, Any]) -> None:
    logger.info("worker_encerrado")


class WorkerSettings:
    """Configuração consumida por `arq app.worker.main.WorkerSettings`."""

    functions: ClassVar[list[Any]] = [ping]
    cron_jobs: ClassVar[list[Any]] = [
        # A cada 30 segundos: comprova processamento, não só processo vivo.
        cron(heartbeat, second={0, 30}, run_at_startup=True),
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    on_startup = ao_iniciar
    on_shutdown = ao_encerrar
    keep_result = 3600
    max_tries = 3
    health_check_interval = 30
    # Evita que um job travado bloqueie a fila indefinidamente.
    job_timeout = 300
