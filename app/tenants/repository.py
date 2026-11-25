"""Acesso a dados de tenant.

Camada fina: só consulta e persiste. Regra de negócio fica em `service.py`.

Regra de isolamento aplicada aqui: **toda** função que lê recurso de tenant
recebe `tenant_id` explicitamente. Não existe `buscar_por_id(id)` sem tenant,
porque essa assinatura convida a vazamento entre contas.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import AmbienteFiscal
from app.db.models.tenant import Tenant, TenantFiscalConfig


async def criar(sessao: AsyncSession, **campos: object) -> Tenant:
    """Persiste um tenant novo."""
    tenant = Tenant(**campos)
    sessao.add(tenant)
    await sessao.flush()
    return tenant


async def por_id(sessao: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
    return await sessao.get(Tenant, tenant_id)


async def por_slug(sessao: AsyncSession, slug: str) -> Tenant | None:
    resultado = await sessao.execute(select(Tenant).where(Tenant.slug == slug))
    return resultado.scalar_one_or_none()


async def por_hash_de_chave(sessao: AsyncSession, chave_hash: str) -> Tenant | None:
    resultado = await sessao.execute(select(Tenant).where(Tenant.api_key_hash == chave_hash))
    return resultado.scalar_one_or_none()


async def listar(sessao: AsyncSession, *, limite: int, deslocamento: int) -> Sequence[Tenant]:
    resultado = await sessao.execute(
        select(Tenant).order_by(Tenant.created_at.desc()).limit(limite).offset(deslocamento)
    )
    return resultado.scalars().all()


async def contar(sessao: AsyncSession) -> int:
    resultado = await sessao.execute(select(func.count()).select_from(Tenant))
    return int(resultado.scalar_one())


async def atualizar_hash_de_chave(
    sessao: AsyncSession, tenant: Tenant, *, prefixo: str, chave_hash: str
) -> Tenant:
    tenant.api_key_prefix = prefixo
    tenant.api_key_hash = chave_hash
    tenant.api_key_rotacionada_em = func.now()  # type: ignore[assignment]
    await sessao.flush()
    return tenant


async def config_do_municipio(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    municipio_ibge: str,
    ambiente: AmbienteFiscal,
) -> TenantFiscalConfig | None:
    resultado = await sessao.execute(
        select(TenantFiscalConfig).where(
            TenantFiscalConfig.tenant_id == tenant_id,
            TenantFiscalConfig.municipio_ibge == municipio_ibge,
            TenantFiscalConfig.ambiente == ambiente,
        )
    )
    return resultado.scalar_one_or_none()


async def listar_configs(
    sessao: AsyncSession, tenant_id: uuid.UUID
) -> Sequence[TenantFiscalConfig]:
    resultado = await sessao.execute(
        select(TenantFiscalConfig)
        .where(TenantFiscalConfig.tenant_id == tenant_id)
        .order_by(TenantFiscalConfig.municipio_ibge)
    )
    return resultado.scalars().all()


async def upsert_config(
    sessao: AsyncSession, tenant_id: uuid.UUID, dados: dict[str, object]
) -> TenantFiscalConfig:
    """Cria ou atualiza a configuração de um município/ambiente."""
    existente = await config_do_municipio(
        sessao,
        tenant_id,
        str(dados["municipio_ibge"]),
        dados["ambiente"],  # type: ignore[arg-type]
    )
    if existente is None:
        config = TenantFiscalConfig(tenant_id=tenant_id, **dados)
        sessao.add(config)
        await sessao.flush()
        return config

    for campo, valor in dados.items():
        setattr(existente, campo, valor)
    await sessao.flush()
    return existente
