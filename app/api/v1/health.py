"""Healthcheck e metadados do serviço.

Distinção deliberada entre dois endpoints:

- ``/health/live`` — o processo está de pé. Nunca toca dependência externa, para
  não derrubar o container em restart loop quando o banco pisca.
- ``/health`` — o serviço consegue trabalhar: banco e Redis respondem. Devolve
  **503** quando algum depende está fora, porque orquestrador precisa saber a
  diferença entre "processo vivo" e "pronto para receber tráfego".
"""

from __future__ import annotations

import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.redis import ping_redis
from app.db.session import ping
from app.versao import APP_VERSION, SCHEMA_RELATORIO

router = APIRouter(tags=["meta"])

HTTP_503 = 503

_INICIO = time.monotonic()


class EstadoDependencia(BaseModel):
    ok: bool
    detalhe: str | None = None


class EstadoWorker(BaseModel):
    """Sinal de vida do worker, lido do batimento em Redis.

    `detalhe` explica a ausência em linguagem de operação, não de stack trace. O valor do
    batimento é um timestamp — não é dado de tenant nem PII.
    """

    ok: bool
    ultimo_batimento: str | None = None
    detalhe: str | None = None


class SaudeOut(BaseModel):
    status: Literal["ok", "degraded"]
    versao: str
    ambiente: str
    uptime_segundos: float
    #: Adaptador NFS-e em uso (`sefin` ou `mock`). Existe para que ninguém confunda uma
    #: instância com dublê ligado com serviço fiscal real — o dublê é indistinguível na
    #: resposta de emissão, de propósito. Não é segredo: é o nome do adaptador, não a
    #: configuração dele.
    nfse_adapter: str
    #: Estado do worker assíncrono (`ADMIN`/fila de webhooks/DLQ). Reportado sempre; só entra na
    #: decisão de 503 quando `READINESS_EXIGE_WORKER=true`.
    worker: EstadoWorker
    verificacoes: dict[str, EstadoDependencia]


class VivoOut(BaseModel):
    status: Literal["ok"]
    versao: str


class VersaoOut(BaseModel):
    versao: str
    schema_relatorio: str
    ambiente: str


async def _estado_worker() -> EstadoWorker:
    """Lê o batimento do worker sem transformar indisponibilidade em exceção.

    A chave é a mesma que `app/worker/main.py` escreve e que `app/worker/healthcheck.py` usa
    no healthcheck do Docker — uma fonte só. Se o Redis não responder, o estado é "não sei",
    reportado como não-ok com o motivo, nunca como sucesso silencioso.
    """
    from app.core.redis import obter_redis
    from app.worker.main import CHAVE_HEARTBEAT

    try:
        valor = await obter_redis().get(CHAVE_HEARTBEAT)
    except Exception as exc:  # Redis fora: reportar, não derrubar a readiness aqui
        return EstadoWorker(
            ok=False, detalhe=f"não foi possível ler o batimento ({type(exc).__name__})"
        )

    if not valor:
        return EstadoWorker(
            ok=False,
            detalhe=(
                "sem batimento do worker: ele pode estar parado ou sem consumir a fila "
                "(webhooks e retentativas não avançam)"
            ),
        )
    texto = valor.decode("utf-8", errors="replace") if isinstance(valor, bytes) else str(valor)
    return EstadoWorker(ok=True, ultimo_batimento=texto)


@router.get(
    "/health/live",
    response_model=VivoOut,
    summary="Liveness: o processo está de pé",
)
async def vivo() -> VivoOut:
    return VivoOut(status="ok", versao=APP_VERSION)


@router.get(
    "/health",
    response_model=SaudeOut,
    summary="Readiness: banco e Redis respondem",
    responses={503: {"description": "Dependência indisponível"}},
)
async def saude(
    resposta: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SaudeOut:
    banco_ok = await ping()
    redis_ok = await ping_redis()
    worker = await _estado_worker()

    verificacoes: dict[str, Any] = {
        "database": EstadoDependencia(
            ok=banco_ok, detalhe=None if banco_ok else "não foi possível executar SELECT 1"
        ),
        "redis": EstadoDependencia(
            ok=redis_ok, detalhe=None if redis_ok else "não foi possível executar PING"
        ),
    }
    tudo_ok = all(v.ok for v in verificacoes.values())
    # O worker só reprova a readiness quando o operador pedir isso explicitamente.
    if settings.readiness_exige_worker and not worker.ok:
        tudo_ok = False
    if not tudo_ok:
        resposta.status_code = HTTP_503

    return SaudeOut(
        status="ok" if tudo_ok else "degraded",
        versao=APP_VERSION,
        ambiente=settings.environment,
        uptime_segundos=round(time.monotonic() - _INICIO, 3),
        nfse_adapter=settings.nfse_adapter,
        worker=worker,
        verificacoes=verificacoes,
    )


@router.get("/version", response_model=VersaoOut, summary="Versão do serviço e do contrato")
async def versao() -> VersaoOut:
    return VersaoOut(
        versao=APP_VERSION,
        schema_relatorio=SCHEMA_RELATORIO,
        ambiente=get_settings().environment,
    )
