"""Dependências HTTP: sessão de banco, tenant autenticado e acesso administrativo.

Autenticação por API key no header `X-API-Key`. O tenant resolvido é a **única**
fonte de `tenant_id` usada pelas rotas — nenhuma rota aceita `tenant_id` vindo do
corpo ou da query, porque isso permitiria a um tenant operar sobre outro.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models.tenant import Tenant
from app.db.session import get_session
from app.tenants import service as tenant_service
from app.tenants.service import (
    CredencialExpirada,
    CredencialInvalida,
    CredencialRevogada,
    TenantSuspenso,
)

logger = logging.getLogger(__name__)

HTTP_401 = 401
HTTP_403 = 403
HTTP_503 = 503


async def tenant_atual(
    x_api_key: str | None = Header(
        default=None, alias="X-API-Key", description="API key do tenant"
    ),
    db: AsyncSession = Depends(get_session),
) -> Tenant:
    """Resolve o tenant dono da API key ou interrompe com 401/403."""
    if not x_api_key:
        raise HTTPException(
            status_code=HTTP_401,
            detail="header X-API-Key ausente",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    try:
        return await tenant_service.autenticar(db, x_api_key)
    except CredencialInvalida as exc:
        raise HTTPException(
            status_code=HTTP_401,
            detail="credencial inválida",
            headers={"WWW-Authenticate": "ApiKey"},
        ) from exc
    except TenantSuspenso as exc:
        raise HTTPException(status_code=HTTP_403, detail="conta suspensa") from exc
    except CredencialRevogada as exc:
        # O portador da chave precisa saber que ela foi revogada: sem isso ele insiste em retry
        # eterno com credencial morta. Não é pista para quem sonda — quem tem a chave já a tem.
        raise HTTPException(
            status_code=HTTP_401,
            detail="credencial revogada; emita outra antes de continuar",
            headers={"WWW-Authenticate": "ApiKey"},
        ) from exc
    except CredencialExpirada as exc:
        raise HTTPException(
            status_code=HTTP_401,
            detail="credencial expirada; rotacione para obter outra",
            headers={"WWW-Authenticate": "ApiKey"},
        ) from exc


async def exigir_admin(
    x_admin_token: str | None = Header(
        default=None, alias="X-Admin-Token", description="Token administrativo"
    ),
    settings: Settings = Depends(get_settings),
) -> None:
    """Protege rotas de bootstrap (criação e listagem de tenants).

    Sem `ADMIN_API_TOKEN` configurado:
    - em desenvolvimento, a rota fica aberta e o acesso é registrado no log;
    - em produção, a rota é recusada com 503, porque conta aberta por qualquer
      um é falha de segurança, não conveniência.
    """
    esperado = settings.admin_api_token.strip()

    if not esperado:
        if settings.is_production:
            raise HTTPException(
                status_code=HTTP_503,
                detail=(
                    "ADMIN_API_TOKEN não configurado; rotas administrativas "
                    "desabilitadas em produção"
                ),
            )
        logger.warning(
            "acesso_administrativo_sem_token",
            extra={"rota": "tenants", "ambiente": settings.environment},
        )
        return

    if not x_admin_token or not hmac.compare_digest(x_admin_token, esperado):
        raise HTTPException(status_code=HTTP_403, detail="token administrativo inválido")
