"""Ciclo de vida do certificado A1 do tenant.

Regras que este módulo garante:

1. **Um certificado ativo por tenant.** Assinar com dois certificados ambíguos é
   convite a erro; ao ativar um novo, o anterior é desativado.
2. **Fingerprint é único por tenant.** Reenviar o mesmo arquivo é 409, não duplicata.
3. **O PFX em claro nunca sai deste módulo.** O que trafega para cima são metadados.
4. **Certificado expirado é aceito no upload, mas sinalizado.** Recusar não
   ajudaria — o usuário precisa ver o motivo, não um erro genérico.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.certificates.cofre import (
    CertificadoA1,
    ErroCertificado,
    abrir_pfx,
    selar_pfx,
)
from app.core.config import Settings, get_settings
from app.db.models.tenant import TenantCertificate

logger = logging.getLogger(__name__)


class ErroDeCertificadoDeTenant(Exception):
    """Base dos erros de domínio do cofre por tenant."""


class CertificadoDuplicado(ErroDeCertificadoDeTenant):
    """O tenant já tem certificado com esta fingerprint."""


class CertificadoNaoEncontrado(ErroDeCertificadoDeTenant):
    """Não existe certificado com este id para este tenant."""


async def registrar(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    apelido: str,
    pfx: bytes,
    senha: str | None = None,
    settings: Settings | None = None,
) -> TenantCertificate:
    """Abre, valida e guarda o certificado selado. Devolve o registro persistido."""
    conf = settings or get_settings()

    try:
        certificado = CertificadoA1.de_pfx(pfx, senha)
    except ErroCertificado:
        raise

    existente = await por_fingerprint(sessao, tenant_id, certificado.fingerprint_sha256)
    if existente is not None:
        raise CertificadoDuplicado(
            f"este certificado já está cadastrado para o tenant (apelido {existente.apelido!r})"
        )

    # Só um ativo por vez: o anterior sai de cena na mesma transação.
    await sessao.execute(
        update(TenantCertificate)
        .where(TenantCertificate.tenant_id == tenant_id, TenantCertificate.ativo.is_(True))
        .values(ativo=False)
    )

    envelope = selar_pfx(
        pfx,
        tenant_id=tenant_id,
        chave=conf.master_key(),
        senha=senha.encode("utf-8") if senha else None,
    )

    registro = TenantCertificate(
        tenant_id=tenant_id,
        apelido=apelido.strip()[:100],
        cnpj=certificado.cnpj,
        subject_cn=certificado.razao_social,
        emissor=certificado.emissor,
        numero_serie=certificado.numero_serie,
        valido_de=certificado.valido_de,
        valido_ate=certificado.valido_ate,
        fingerprint_sha256=certificado.fingerprint_sha256,
        pfx_selado=envelope,
        senha_selada=None,
        ativo=True,
    )
    sessao.add(registro)
    await sessao.flush()

    if certificado.expirado:
        logger.warning(
            "certificado_expirado_cadastrado",
            extra={"tenant_id": str(tenant_id), "valido_ate": certificado.valido_ate.isoformat()},
        )
    if certificado.dias_restantes <= 30 and not certificado.expirado:
        logger.warning(
            "certificado_perto_de_expirar",
            extra={"tenant_id": str(tenant_id), "dias_restantes": certificado.dias_restantes},
        )

    return registro


async def por_fingerprint(
    sessao: AsyncSession, tenant_id: uuid.UUID, fingerprint: str
) -> TenantCertificate | None:
    resultado = await sessao.execute(
        select(TenantCertificate).where(
            TenantCertificate.tenant_id == tenant_id,
            TenantCertificate.fingerprint_sha256 == fingerprint,
        )
    )
    return resultado.scalar_one_or_none()


async def listar(sessao: AsyncSession, tenant_id: uuid.UUID) -> Sequence[TenantCertificate]:
    resultado = await sessao.execute(
        select(TenantCertificate)
        .where(TenantCertificate.tenant_id == tenant_id)
        .order_by(TenantCertificate.created_at.desc())
    )
    return resultado.scalars().all()


async def ativo(sessao: AsyncSession, tenant_id: uuid.UUID) -> TenantCertificate | None:
    """Certificado ativo do tenant, se houver."""
    resultado = await sessao.execute(
        select(TenantCertificate).where(
            TenantCertificate.tenant_id == tenant_id,
            TenantCertificate.ativo.is_(True),
        )
    )
    return resultado.scalars().first()


async def por_id(
    sessao: AsyncSession, tenant_id: uuid.UUID, certificado_id: uuid.UUID
) -> TenantCertificate:
    resultado = await sessao.execute(
        select(TenantCertificate).where(
            TenantCertificate.tenant_id == tenant_id,
            TenantCertificate.id == certificado_id,
        )
    )
    registro = resultado.scalar_one_or_none()
    if registro is None:
        raise CertificadoNaoEncontrado(f"certificado {certificado_id} não encontrado")
    return registro


async def ativar(
    sessao: AsyncSession, tenant_id: uuid.UUID, certificado_id: uuid.UUID
) -> TenantCertificate:
    registro = await por_id(sessao, tenant_id, certificado_id)
    await sessao.execute(
        update(TenantCertificate)
        .where(TenantCertificate.tenant_id == tenant_id, TenantCertificate.ativo.is_(True))
        .values(ativo=False)
    )
    registro.ativo = True
    await sessao.flush()
    return registro


async def remover(sessao: AsyncSession, tenant_id: uuid.UUID, certificado_id: uuid.UUID) -> None:
    registro = await por_id(sessao, tenant_id, certificado_id)
    await sessao.delete(registro)
    await sessao.flush()


async def remover_todos(sessao: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Apaga todos os certificados do tenant (uso em exclusão de conta)."""
    registros = await listar(sessao, tenant_id)
    for registro in registros:
        await sessao.delete(registro)
    await sessao.flush()
    return len(registros)


def abrir_em_memoria(
    registro: TenantCertificate, *, settings: Settings | None = None
) -> CertificadoA1:
    """Descriptografa e abre o certificado, **apenas em memória**.

    Chamado no momento da assinatura. O objeto devolvido carrega chave privada em
    claro: não logar, não serializar, não guardar em cache além do necessário.
    """
    conf = settings or get_settings()
    pfx, senha = abrir_pfx(
        registro.pfx_selado,
        tenant_id=registro.tenant_id,
        chave=conf.master_key(),
        tem_senha=True,
    )
    return CertificadoA1.de_pfx(pfx, senha)
