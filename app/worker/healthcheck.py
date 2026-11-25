"""Healthcheck do worker.

Executado pelo Docker como ``python -m app.worker.healthcheck``. Sai com 0 quando
o batimento está fresco e 1 quando não está.

Por que não basta "processo de pé": o `arq` pode continuar rodando com a conexão
Redis perdida, sem consumir job nenhum. Olhar o batimento prova que o laço de
processamento está vivo.
"""

from __future__ import annotations

import asyncio
import sys

from app.core.redis import fechar_redis, obter_redis
from app.worker.main import CHAVE_HEARTBEAT


async def verificar() -> int:
    try:
        valor = await obter_redis().get(CHAVE_HEARTBEAT)
    except Exception as exc:
        print(f"worker unhealthy: redis inacessível ({type(exc).__name__})", file=sys.stderr)
        return 1
    finally:
        await fechar_redis()

    if not valor:
        print(
            f"worker unhealthy: chave {CHAVE_HEARTBEAT} ausente ou expirada "
            "(worker parado ou sem processar)",
            file=sys.stderr,
        )
        return 1

    print(f"worker healthy: último batimento {valor}")
    return 0


def main() -> int:
    return asyncio.run(verificar())


if __name__ == "__main__":
    raise SystemExit(main())
