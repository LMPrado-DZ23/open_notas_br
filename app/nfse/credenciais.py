"""Credenciais municipais: selar, abrir e reservar número de RPS.

Duas responsabilidades que falham em silêncio se implementadas de forma ingênua:

**AAD.** O `aad` amarra o ciphertext a `tenant_id` + `codigo_ibge`. Um blob copiado de
um tenant para outro **não abre** — o GCM falha na autenticação. Sem o AAD por município,
duas prefeituras do mesmo tenant compartilhariam contexto, e um dump restaurado no lugar
errado decifraria.

**Numeração.** `reservar_numero_rps` usa `SELECT ... FOR UPDATE`. Sem o lock, duas
emissões simultâneas leem o mesmo `ultimo_numero_rps`, geram RPS com o mesmo número, e a
prefeitura recusa a segunda por duplicidade. É falha intermitente: passa no teste, aparece
com carga.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import Cofre, aad_do_tenant
from app.db.models.credencial_municipal import CredencialMunicipalTenant


class ErroCredencial(Exception):
    """Credencial ausente, inativa ou incoerente."""


def _aad(tenant_id: uuid.UUID, codigo_ibge: str) -> bytes:
    """AAD do município: tenant + IBGE. Muda o município, muda o AAD."""
    return aad_do_tenant(tenant_id) + b"|" + codigo_ibge.encode("utf-8")


async def por_municipio(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, codigo_ibge: str
) -> CredencialMunicipalTenant | None:
    consulta = select(CredencialMunicipalTenant).where(
        CredencialMunicipalTenant.tenant_id == tenant_id,
        CredencialMunicipalTenant.codigo_ibge == codigo_ibge,
    )
    return (await sessao.execute(consulta)).scalar_one_or_none()


async def salvar(
    sessao: AsyncSession,
    *,
    cofre: Cofre,
    tenant_id: uuid.UUID,
    codigo_ibge: str,
    inscricao_municipal: str | None = None,
    usuario_ws: str | None = None,
    senha_ws: str | None = None,
    token_ws: str | None = None,
    serie_rps_padrao: str = "1",
) -> CredencialMunicipalTenant:
    """Cria ou atualiza selando os segredos.

    Segredo `None` **preserva** o valor anterior: rotacionar só a senha não pode apagar
    o token que já estava lá.
    """
    aad = _aad(tenant_id, codigo_ibge)
    credencial = await por_municipio(sessao, tenant_id=tenant_id, codigo_ibge=codigo_ibge)

    if credencial is None:
        credencial = CredencialMunicipalTenant(tenant_id=tenant_id, codigo_ibge=codigo_ibge)
        sessao.add(credencial)

    credencial.inscricao_municipal = inscricao_municipal or credencial.inscricao_municipal
    credencial.serie_rps_padrao = serie_rps_padrao or credencial.serie_rps_padrao
    if usuario_ws is not None:
        credencial.usuario_ws_criptografado = cofre.selar(usuario_ws.encode(), aad=aad)
    if senha_ws is not None:
        credencial.senha_ws_criptografada = cofre.selar(senha_ws.encode(), aad=aad)
    if token_ws is not None:
        credencial.token_ws_criptografado = cofre.selar(token_ws.encode(), aad=aad)

    await sessao.flush()
    return credencial


#: Nome da coluna por campo lógico. Mapa explícito porque concatenar sufixo quebra:
#: "usuario" é masculino (`_criptografado`) e "senha" é feminino (`_criptografada`).
#: Bug pego pelo teste — a concatenação devolvia None em silêncio para senha.
COLUNA_DO_CAMPO = {
    "usuario_ws": "usuario_ws_criptografado",
    "senha_ws": "senha_ws_criptografada",
    "token_ws": "token_ws_criptografado",
}


def segredo(credencial: CredencialMunicipalTenant, campo: str, *, cofre: Cofre) -> str | None:
    """Abre um segredo. Campo inexistente ou vazio devolve `None`, não erro."""
    if campo not in COLUNA_DO_CAMPO:
        raise ValueError(f"campo de segredo desconhecido: {campo}")
    envelope = getattr(credencial, COLUNA_DO_CAMPO[campo], None)
    if not envelope:
        return None
    aad = _aad(credencial.tenant_id, credencial.codigo_ibge)
    return cofre.abrir(envelope, aad=aad).decode()


async def reservar_numero_rps(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, codigo_ibge: str
) -> int:
    """Reserva o próximo número de RPS com lock de linha.

    `with_for_update()` na leitura: a segunda transação espera a primeira commitar e lê
    o número já incrementado. Sem isso, as duas leem o mesmo valor.
    """
    consulta = (
        select(CredencialMunicipalTenant)
        .where(
            CredencialMunicipalTenant.tenant_id == tenant_id,
            CredencialMunicipalTenant.codigo_ibge == codigo_ibge,
        )
        .with_for_update()
    )
    credencial = (await sessao.execute(consulta)).scalar_one_or_none()
    if credencial is None:
        raise ErroCredencial(
            f"sem credencial para o município {codigo_ibge}; cadastre antes de emitir"
        )
    if not credencial.ativa:
        raise ErroCredencial(f"credencial do município {codigo_ibge} está inativa")

    credencial.ultimo_numero_rps += 1
    await sessao.flush()
    return credencial.ultimo_numero_rps


async def desativar(sessao: AsyncSession, *, tenant_id: uuid.UUID, codigo_ibge: str) -> bool:
    """Marca inativa. Não apaga: a credencial precisa continuar ligada às notas emitidas."""
    credencial = await por_municipio(sessao, tenant_id=tenant_id, codigo_ibge=codigo_ibge)
    if credencial is None:
        return False
    credencial.ativa = False
    await sessao.flush()
    return True
