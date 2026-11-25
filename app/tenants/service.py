"""Regras de negócio de tenant.

Duas invariantes que este módulo protege:

1. Slug é único globalmente — é o identificador que o parceiro usa na URL.
2. A API key em claro só existe no instante da criação/rotação. Depois disso, o
   servidor só conhece o hash. Não há "recuperar chave".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import aad_do_tenant
from app.core.security import (
    gerar_api_key,
    gerar_segredo_webhook,
    hash_api_key,
)
from app.core.vault import selar
from app.db.models.enums import StatusTenant
from app.db.models.tenant import Tenant, TenantFiscalConfig
from app.tenants import repository as repo
from app.tenants.schemas import TenantCreate


class ErroDeTenant(Exception):
    """Base dos erros de domínio de tenant."""


class SlugJaExiste(ErroDeTenant):
    """Já existe tenant com o slug informado."""


class TenantSuspenso(ErroDeTenant):
    """O tenant existe, mas está suspenso."""


class CredencialInvalida(ErroDeTenant):
    """API key desconhecida."""


async def criar_tenant(sessao: AsyncSession, dados: TenantCreate) -> tuple[Tenant, str, str | None]:
    """Cria tenant, API key e segredo de webhook.

    Devolve ``(tenant, api_key_em_claro, webhook_secret_em_claro)``. Os dois
    segredos não são recuperáveis depois desta chamada.
    """
    if await repo.por_slug(sessao, dados.slug) is not None:
        raise SlugJaExiste(f"já existe tenant com o slug {dados.slug!r}")

    chave_completa, prefixo, chave_hash = gerar_api_key()

    segredo_webhook: str | None = None
    if dados.webhook_url:
        # Gerado agora, selado depois do flush: o aad amarra o segredo ao id do
        # tenant, e o id só existe após o INSERT.
        segredo_webhook = gerar_segredo_webhook()

    tenant = Tenant(
        slug=dados.slug,
        nome=dados.nome,
        email_contato=str(dados.email_contato) if dados.email_contato else None,
        status=StatusTenant.ATIVO,
        api_key_prefix=prefixo,
        api_key_hash=chave_hash,
        webhook_url=dados.webhook_url,
    )

    try:
        sessao.add(tenant)
        await sessao.flush()
    except IntegrityError as exc:
        await sessao.rollback()
        raise SlugJaExiste(f"já existe tenant com o slug {dados.slug!r}") from exc

    if dados.webhook_url and segredo_webhook is not None:
        tenant.webhook_secret_selado = selar(
            segredo_webhook.encode("utf-8"), aad=aad_do_tenant(tenant.id)
        )
        await sessao.flush()

    return tenant, chave_completa, segredo_webhook


async def autenticar(sessao: AsyncSession, api_key: str) -> Tenant:
    """Resolve o tenant dono da API key.

    Levanta `CredencialInvalida` para chave desconhecida e `TenantSuspenso` para
    conta suspensa. A mensagem não distingue "não existe" de "tem formato errado"
    para não dar pista a quem sonda.
    """
    if not api_key or len(api_key) < 16:
        raise CredencialInvalida("API key ausente ou com formato inválido")

    hash_recebido = hash_api_key(api_key)
    tenant = await repo.por_hash_de_chave(sessao, hash_recebido)
    if tenant is None:
        raise CredencialInvalida("API key inválida")

    if tenant.status is not StatusTenant.ATIVO:
        raise TenantSuspenso("conta suspensa")

    return tenant


async def rotacionar_chave(sessao: AsyncSession, tenant_id: uuid.UUID) -> tuple[Tenant, str]:
    """Gera nova API key e invalida a anterior."""
    tenant = await repo.por_id(sessao, tenant_id)
    if tenant is None:
        raise ErroDeTenant(f"tenant {tenant_id} não encontrado")

    chave_completa, prefixo, chave_hash = gerar_api_key()
    tenant.api_key_prefix = prefixo
    tenant.api_key_hash = chave_hash
    tenant.api_key_rotacionada_em = datetime.now(UTC)
    await sessao.flush()
    return tenant, chave_completa


async def definir_config_fiscal(
    sessao: AsyncSession, tenant_id: uuid.UUID, dados: dict[str, object]
) -> TenantFiscalConfig:
    """Cria ou atualiza a configuração fiscal do município/ambiente."""
    return await repo.upsert_config(sessao, tenant_id, dados)


async def obter_tenant(sessao: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await repo.por_id(sessao, tenant_id)
    if tenant is None:
        raise ErroDeTenant(f"tenant {tenant_id} não encontrado")
    return tenant
