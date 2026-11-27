"""Rotas do cofre de certificados A1.

O upload recebe o `.pfx` e a senha, abre o certificado, extrai metadados, sela com
AES-256-GCM e **descarta** o arquivo em claro. A resposta nunca inclui o PFX.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import tenant_atual
from app.certificates import service
from app.certificates.cofre import ErroCertificado
from app.certificates.schemas import CertificadoOut, SaudeCertificadoOut
from app.certificates.service import CertificadoDuplicado, CertificadoNaoEncontrado
from app.db.models.certificado_uso import CertificadoUso
from app.db.models.tenant import Tenant
from app.db.session import get_session

HTTP_409 = 409
HTTP_413 = 413
HTTP_422 = 422

#: PFX é arquivo pequeno. Limite apertado evita upload acidental de outra coisa.
TAMANHO_MAXIMO_PFX = 1024 * 1024


class UsoCertificadoOut(BaseModel):
    """Uma linha de auditoria de uso. Sem mensagem de erro, sem segredo, sem XML."""

    id: uuid.UUID
    operacao: str
    ambiente: str | None = None
    sucesso: bool
    erro_tipo: str | None = None
    em: datetime


router = APIRouter(tags=["certificados"])


def _saida(registro) -> CertificadoOut:
    dias = None
    if registro.valido_ate is not None:
        validade = registro.valido_ate
        if validade.tzinfo is None:
            validade = validade.replace(tzinfo=UTC)
        dias = (validade - datetime.now(UTC)).days
    dados = CertificadoOut.model_validate(registro)
    return dados.model_copy(update={"dias_restantes": dias})


@router.post(
    "/me/certificados",
    response_model=CertificadoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Envia o certificado A1 (.pfx/.p12) e sela no cofre",
)
async def enviar_certificado(
    arquivo: UploadFile = File(..., description="Arquivo .pfx ou .p12"),
    senha: str = Form(..., description="Senha do certificado"),
    apelido: str = Form(..., min_length=1, max_length=100),
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> CertificadoOut:
    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(status_code=HTTP_422, detail="arquivo vazio")
    if len(conteudo) > TAMANHO_MAXIMO_PFX:
        raise HTTPException(
            status_code=HTTP_413,
            detail=f"arquivo tem {len(conteudo)} bytes; o limite é {TAMANHO_MAXIMO_PFX}",
        )

    try:
        registro = await service.registrar(
            db, tenant.id, apelido=apelido, pfx=conteudo, senha=senha
        )
        await db.commit()
    except CertificadoDuplicado as exc:
        await db.rollback()
        raise HTTPException(status_code=HTTP_409, detail=str(exc)) from exc
    except ErroCertificado as exc:
        await db.rollback()
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc

    await db.refresh(registro)
    return _saida(registro)


@router.get(
    "/me/certificados",
    response_model=list[CertificadoOut],
    summary="Lista os certificados do tenant",
)
async def listar_certificados(
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> list[CertificadoOut]:
    registros = await service.listar(db, tenant.id)
    return [_saida(r) for r in registros]


@router.get(
    "/me/certificados/saude",
    response_model=SaudeCertificadoOut,
    summary="Diagnóstico do certificado ativo",
)
async def saude_certificado(
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> SaudeCertificadoOut:
    registro = await service.ativo(db, tenant.id)
    if registro is None:
        return SaudeCertificadoOut(
            existe=False, aviso="nenhum certificado ativo; a emissão não funciona sem ele"
        )
    saida = _saida(registro)
    aviso = None
    if saida.dias_restantes is not None:
        if saida.dias_restantes < 0:
            aviso = "certificado expirado: a SEFIN recusará o aperto de mão TLS"
        elif saida.dias_restantes <= 30:
            aviso = f"certificado expira em {saida.dias_restantes} dias"
    return SaudeCertificadoOut(
        existe=True,
        apelido=saida.apelido,
        cnpj=saida.cnpj,
        valido_ate=saida.valido_ate,
        dias_restantes=saida.dias_restantes,
        expirado=(saida.dias_restantes is not None and saida.dias_restantes < 0),
        aviso=aviso,
    )


@router.post(
    "/me/certificados/{certificado_id}/ativar",
    response_model=CertificadoOut,
    summary="Ativa um certificado (desativa os demais)",
)
async def ativar_certificado(
    certificado_id: uuid.UUID,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> CertificadoOut:
    try:
        registro = await service.ativar(db, tenant.id, certificado_id)
        await db.commit()
    except CertificadoNaoEncontrado as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.refresh(registro)
    return _saida(registro)


@router.delete(
    "/me/certificados/{certificado_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove o certificado do cofre",
)
async def remover_certificado(
    certificado_id: uuid.UUID,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> None:
    try:
        await service.remover(db, tenant.id, certificado_id)
        await db.commit()
    except CertificadoNaoEncontrado as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/me/certificados/{certificado_id}/usos",
    response_model=list[UsoCertificadoOut],
    summary="Histórico de uso do certificado (auditoria)",
)
async def usos_do_certificado(
    certificado_id: uuid.UUID,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
    limite: int = Query(default=50, ge=1, le=200),
) -> list[UsoCertificadoOut]:
    """Quem usou este A1, quando e para qual operação (§71).

    `404` quando o certificado não é do tenant: a existência de um id de outro cliente não é
    informação que este endpoint deva revelar.

    O registro traz operação, ambiente, sucesso e o **tipo** do erro — nunca mensagem, nunca
    segredo, nunca XML. É auditoria de uso, não cópia da operação.
    """
    try:
        await service.por_id(db, tenant.id, certificado_id)
    except CertificadoNaoEncontrado:
        raise HTTPException(status_code=404, detail="certificado não encontrado") from None

    linhas = (
        (
            await db.execute(
                select(CertificadoUso)
                .where(
                    CertificadoUso.tenant_id == tenant.id,
                    CertificadoUso.certificado_id == certificado_id,
                )
                .order_by(CertificadoUso.created_at.desc())
                .limit(limite)
            )
        )
        .scalars()
        .all()
    )
    return [
        UsoCertificadoOut(
            id=linha.id,
            operacao=linha.operacao,
            ambiente=linha.ambiente,
            sucesso=linha.sucesso,
            erro_tipo=linha.erro_tipo,
            em=linha.created_at,
        )
        for linha in linhas
    ]
