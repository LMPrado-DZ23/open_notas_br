"""Rotas de tenant.

Duas famílias:

- **Administrativas** (``/v1/tenants``): criação e listagem, protegidas por
  `X-Admin-Token`. São de bootstrap/operação, não de uso normal.
- **Do próprio tenant** (``/v1/me``): autenticadas por API key. O `tenant_id`
  vem sempre do token, nunca do corpo — é o que impede um tenant de ler ou
  alterar dados de outro.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import exigir_admin, tenant_atual
from app.db.models.tenant import Tenant
from app.db.session import get_session
from app.tenants import repository as repo
from app.tenants import service
from app.tenants.schemas import (
    PaginaTenants,
    TenantCreate,
    TenantCriadoOut,
    TenantFiscalConfigIn,
    TenantFiscalConfigOut,
    TenantKeyRotacionadaOut,
    TenantOut,
)
from app.tenants.service import SlugJaExiste

HTTP_409 = 409

router = APIRouter(tags=["tenants"])


@router.post(
    "/tenants",
    response_model=TenantCriadoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cria um tenant e devolve a API key (uma única vez)",
    dependencies=[Depends(exigir_admin)],
)
async def criar_tenant(
    dados: TenantCreate,
    db: AsyncSession = Depends(get_session),
) -> TenantCriadoOut:
    try:
        tenant, api_key, webhook_secret = await service.criar_tenant(db, dados)
        await db.commit()
    except SlugJaExiste as exc:
        await db.rollback()
        raise HTTPException(status_code=HTTP_409, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=HTTP_409, detail="violação de unicidade ao criar tenant"
        ) from exc

    base = TenantOut.model_validate(tenant)
    return TenantCriadoOut(
        **base.model_dump(),
        api_key=api_key,
        webhook_secret=webhook_secret,
    )


@router.get(
    "/tenants",
    response_model=PaginaTenants,
    summary="Lista tenants (administrativo)",
    dependencies=[Depends(exigir_admin)],
)
async def listar_tenants(
    limite: int = Query(default=50, ge=1, le=200),
    deslocamento: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
) -> PaginaTenants:
    itens = await repo.listar(db, limite=limite, deslocamento=deslocamento)
    total = await repo.contar(db)
    return PaginaTenants(
        total=total,
        limite=limite,
        deslocamento=deslocamento,
        itens=[TenantOut.model_validate(t) for t in itens],
    )


@router.get("/me", response_model=TenantOut, summary="Dados do tenant autenticado")
async def meu_tenant(tenant: Tenant = Depends(tenant_atual)) -> TenantOut:
    return TenantOut.model_validate(tenant)


@router.post(
    "/me/rotacionar-chave",
    response_model=TenantKeyRotacionadaOut,
    summary="Gera nova API key e invalida a anterior",
)
async def rotacionar_chave(
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> TenantKeyRotacionadaOut:
    atualizado, nova_chave = await service.rotacionar_chave(db, tenant.id)
    await db.commit()
    return TenantKeyRotacionadaOut(
        tenant_id=atualizado.id,
        api_key=nova_chave,
        api_key_prefix=atualizado.api_key_prefix,
    )


@router.put(
    "/me/config-fiscal",
    response_model=TenantFiscalConfigOut,
    summary="Cria ou atualiza a configuração fiscal de um município",
)
async def definir_config_fiscal(
    dados: TenantFiscalConfigIn,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> TenantFiscalConfigOut:
    payload = dados.model_dump()
    config = await service.definir_config_fiscal(db, tenant.id, payload)
    await db.commit()
    await db.refresh(config)
    return TenantFiscalConfigOut.model_validate(config)


@router.get(
    "/me/config-fiscal",
    response_model=list[TenantFiscalConfigOut],
    summary="Lista as configurações fiscais do tenant",
)
async def listar_config_fiscal(
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> list[TenantFiscalConfigOut]:
    configs = await repo.listar_configs(db, tenant.id)
    return [TenantFiscalConfigOut.model_validate(c) for c in configs]
