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
from typing import Any, Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.redis import ping_redis
from app.db.session import ping
from app.versao import APP_VERSION, SCHEMA_RELATORIO

router = APIRouter(tags=["meta"])

HTTP_503 = 503

_INICIO = time.monotonic()


class EstadoDependencia(BaseModel):
    ok: bool
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
    verificacoes: dict[str, EstadoDependencia]


class VivoOut(BaseModel):
    status: Literal["ok"]
    versao: str


class VersaoOut(BaseModel):
    versao: str
    schema_relatorio: str
    ambiente: str


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
async def saude(resposta: Response) -> SaudeOut:
    settings = get_settings()

    banco_ok = await ping()
    redis_ok = await ping_redis()

    verificacoes: dict[str, Any] = {
        "database": EstadoDependencia(
            ok=banco_ok, detalhe=None if banco_ok else "não foi possível executar SELECT 1"
        ),
        "redis": EstadoDependencia(
            ok=redis_ok, detalhe=None if redis_ok else "não foi possível executar PING"
        ),
    }
    tudo_ok = all(v.ok for v in verificacoes.values())
    if not tudo_ok:
        resposta.status_code = HTTP_503

    return SaudeOut(
        status="ok" if tudo_ok else "degraded",
        versao=APP_VERSION,
        ambiente=settings.environment,
        uptime_segundos=round(time.monotonic() - _INICIO, 3),
        nfse_adapter=settings.nfse_adapter,
        verificacoes=verificacoes,
    )


@router.get("/version", response_model=VersaoOut, summary="Versão do serviço e do contrato")
async def versao() -> VersaoOut:
    return VersaoOut(
        versao=APP_VERSION,
        schema_relatorio=SCHEMA_RELATORIO,
        ambiente=get_settings().environment,
    )
