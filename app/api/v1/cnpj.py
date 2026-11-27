"""Rotas de consulta de CNPJ.

Distingue três resultados, porque confundir os dois primeiros faz o usuário
"corrigir" um dado que está certo:

- ``422`` CNPJ inválido (falha de forma: tamanho ou DV).
- ``404`` CNPJ válido que as fontes não conhecem.
- ``503`` as fontes não responderam (transitório: tentar de novo).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import tenant_atual
from app.cnpj.client import (
    BrasilApiCnpj,
    CnpjInvalido,
    CnpjNaoEncontrado,
    ConsultaCnpj,
    FonteIndisponivel,
    MinhaReceitaCnpj,
    SerproCnpj,
)
from app.cnpj.service import ServicoCnpj
from app.core.config import Settings, get_settings
from app.core.redis import obter_redis

HTTP_404 = 404
HTTP_422 = 422
HTTP_503 = 503

router = APIRouter(tags=["cnpj"])


def montar_servico(settings: Settings) -> ServicoCnpj:
    """Monta a cadeia de fontes conforme configuração.

    Ordem: Serpro (se houver token, é a fonte oficial e tem cota) e depois as
    públicas. Com `CNPJ_FALLBACK_ENABLED=false`, só a Serpro é usada.
    """
    # Anotação explícita: `list` é invariante no mypy, então uma lista inferida como
    # `SerproCnpj` não aceita as fontes públicas. O tipo correto é a interface comum.
    fontes: list[ConsultaCnpj] = []
    if settings.serpro_cnpj_token:
        fontes.append(
            SerproCnpj(token=settings.serpro_cnpj_token, base_url=settings.serpro_cnpj_base_url)
        )
    if settings.cnpj_fallback_enabled or not fontes:
        fontes.append(BrasilApiCnpj())
        fontes.append(MinhaReceitaCnpj())

    return ServicoCnpj(
        fontes,
        redis=obter_redis(),
        ttl_segundos=settings.cnpj_cache_ttl_seconds,
    )


@router.get(
    "/cnpj/{cnpj}",
    summary="Consulta e enriquece um CNPJ (cache + fontes públicas)",
    responses={
        404: {"description": "CNPJ válido não encontrado nas fontes"},
        422: {"description": "CNPJ inválido"},
        503: {"description": "Fontes indisponíveis"},
    },
)
async def consultar_cnpj(
    cnpj: str,
    usar_cache: Annotated[bool, Query(description="Permite ignorar o cache")] = True,
    settings: Settings = Depends(get_settings),
    _tenant=Depends(tenant_atual),
) -> dict:
    servico = montar_servico(settings)
    try:
        resultado = await servico.consultar(cnpj, usar_cache=usar_cache)
    except CnpjInvalido as exc:
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc
    except CnpjNaoEncontrado as exc:
        raise HTTPException(status_code=HTTP_404, detail=str(exc)) from exc
    except FonteIndisponivel as exc:
        raise HTTPException(
            status_code=HTTP_503,
            detail={"mensagem": str(exc), "transitorio": True},
        ) from exc

    return resultado.to_dict()
