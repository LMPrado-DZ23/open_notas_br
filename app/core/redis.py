"""Cliente Redis compartilhado.

Um pool por processo, criado sob demanda. `ping` é usado pelo healthcheck.

O cliente é recriado quando o event loop muda. Não é preciosismo: um cliente
`redis.asyncio` carrega conexões amarradas ao loop que as abriu, e reutilizá-lo em
outro loop produz `Event loop is closed` na primeira operação. Isso acontece em
teste (um loop por função) e em qualquer processo que reinicie o loop — melhor
tratar aqui do que deixar o sintoma aparecer como "Redis indisponível".
"""

from __future__ import annotations

import asyncio
import logging

from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis: Redis | None = None
_loop: asyncio.AbstractEventLoop | None = None


def obter_redis() -> Redis:
    """Cliente Redis do processo, ligado ao event loop corrente."""
    global _redis, _loop

    loop_atual = asyncio.get_running_loop()
    if _redis is None or _loop is not loop_atual:
        _redis = Redis.from_url(
            get_settings().redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        _loop = loop_atual
    return _redis


async def ping_redis() -> bool:
    """True se o Redis responde a PING."""
    try:
        resposta = await obter_redis().ping()
        return bool(resposta)
    except Exception as exc:
        logger.warning("redis_indisponivel", extra={"erro": str(exc)})
        return False


async def fechar_redis() -> None:
    """Fecha o pool no shutdown (ou ao trocar de event loop)."""
    global _redis, _loop
    if _redis is not None:
        await _redis.aclose()
    _redis = None
    _loop = None
