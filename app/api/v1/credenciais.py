"""Gestão de credenciais municipais por tenant.

Todas as rotas exigem autenticação e o `tenant_id` vem **da API key**, nunca do corpo
(R6). Credencial de outro tenant responde 404, não 403 — 403 já diria que existe.

O cofre é obtido por `obter_cofre(settings)`: a chave mestra não aparece em request nem
em resposta, e o segredo nunca é devolvido — só o fato de estar ou não cadastrado.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import tenant_atual
from app.core.config import Settings, get_settings
from app.core.vault import obter_cofre
from app.db.models.credencial_municipal import CredencialMunicipalTenant
from app.db.models.municipio import MunicipioNFSe
from app.db.models.tenant import Tenant
from app.db.session import get_session
from app.nfse import credenciais as svc

router = APIRouter(prefix="/credenciais-municipais", tags=["credenciais"])


class CredencialIn(BaseModel):
    """Dados de entrada. Segredo só entra, nunca sai."""

    codigo_ibge: str = Field(min_length=7, max_length=7, pattern=r"^\d{7}$")
    inscricao_municipal: str | None = Field(default=None, max_length=20)
    usuario_ws: str | None = Field(default=None, max_length=200)
    senha_ws: str | None = Field(default=None, max_length=200)
    token_ws: str | None = Field(default=None, max_length=500)
    serie_rps_padrao: str = Field(default="1", max_length=5)


def _serializar(credencial: CredencialMunicipalTenant) -> dict:
    """Nunca inclui segredo nem ciphertext — só a existência de cada campo."""
    return {
        "codigo_ibge": credencial.codigo_ibge,
        "inscricao_municipal": credencial.inscricao_municipal,
        "serie_rps_padrao": credencial.serie_rps_padrao,
        "ultimo_numero_rps": credencial.ultimo_numero_rps,
        "ativa": credencial.ativa,
        "tem_usuario": bool(credencial.usuario_ws_criptografado),
        "tem_senha": bool(credencial.senha_ws_criptografada),
        "tem_token": bool(credencial.token_ws_criptografado),
    }


@router.get("")
async def listar(
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> dict:
    consulta = select(CredencialMunicipalTenant).where(
        CredencialMunicipalTenant.tenant_id == tenant.id
    )
    credenciais = (await db.execute(consulta)).scalars().all()
    return {"itens": [_serializar(c) for c in credenciais], "total": len(credenciais)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def salvar(
    dados: CredencialIn,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Cria ou atualiza. Só aceita município que existe no cadastro."""
    municipio = (
        await db.execute(
            select(MunicipioNFSe).where(MunicipioNFSe.codigo_ibge == dados.codigo_ibge)
        )
    ).scalar_one_or_none()
    if municipio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"município {dados.codigo_ibge} não está no cadastro; consulte GET /v1/municipios"
            ),
        )

    credencial = await svc.salvar(
        db,
        cofre=obter_cofre(settings),
        tenant_id=tenant.id,
        codigo_ibge=dados.codigo_ibge,
        inscricao_municipal=dados.inscricao_municipal,
        usuario_ws=dados.usuario_ws,
        senha_ws=dados.senha_ws,
        token_ws=dados.token_ws,
        serie_rps_padrao=dados.serie_rps_padrao,
    )
    await db.commit()
    return _serializar(credencial)


@router.delete("/{codigo_ibge}")
async def desativar(
    codigo_ibge: str,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Desativa. Não apaga: a credencial continua ligada às notas já emitidas."""
    if not await svc.desativar(db, tenant_id=tenant.id, codigo_ibge=codigo_ibge):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="credencial não encontrada"
        )
    await db.commit()
    return {"codigo_ibge": codigo_ibge, "ativa": False}
