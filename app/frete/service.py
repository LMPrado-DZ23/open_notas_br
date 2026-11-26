"""Serviço de credencial do Melhor Envio: estado do OAuth, cofre e cliente.

Decisões que valem registro:

- **O `state` é assinado, não sorteado.** Ele carrega o `tenant_id` e um carimbo de
  tempo, assinados com a chave-mestra. Assim o callback sabe a qual loja pertence o
  `code` **sem** guardar sessão, e um `state` forjado não passa. Sem isso, o código
  de autorização de uma loja poderia ser trocado pela conta de outra.
- **A renovação acontece no serviço, não no cliente.** O cliente HTTP não guarda
  token; quem persiste é este módulo, e ele renova antes de entregar o cliente. Um
  token vencido nunca chega numa operação de compra.
- **Sandbox é registrado na credencial.** Autorizar no sandbox e comprar em produção
  é erro caro; misturar os dois é recusado em vez de "funcionar torto".
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.crypto import Cofre, aad_do_tenant
from app.db.models.frete import FreteCredencial
from app.frete.client import MelhorEnvioClient
from app.frete.oauth import ErroDeAutorizacao, TokenOAuth, renovar, trocar_codigo

logger = logging.getLogger(__name__)

#: Janela do `state`. Autorização é ato de minutos, não de horas.
VALIDADE_ESTADO = 15 * 60


class ErroDeFrete(Exception):
    """Falha de configuração ou de credencial do frete."""


class NaoAutorizado(ErroDeFrete):
    """O lojista ainda não autorizou o aplicativo (ou revogou)."""


class EstadoInvalido(ErroDeFrete):
    """`state` do callback inválido, expirado ou de outro tenant."""


def _chave(settings: Settings) -> bytes:
    return settings.master_key()


def _cofre(settings: Settings) -> Cofre:
    return Cofre(_chave(settings))


def _assinar(payload: str, settings: Settings) -> str:
    assinatura = hmac.new(_chave(settings), payload.encode(), hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(assinatura).decode().rstrip("=")


def gerar_estado(tenant_id: uuid.UUID, settings: Settings | None = None) -> str:
    """`state` assinado: `<tenant>.<timestamp>.<assinatura>`."""
    conf = settings or get_settings()
    payload = f"{tenant_id}.{int(time.time())}"
    return f"{payload}.{_assinar(payload, conf)}"


def ler_estado(state: str, settings: Settings | None = None) -> uuid.UUID:
    """Valida o `state` e devolve o tenant. Levanta se algo não confere."""
    conf = settings or get_settings()
    partes = (state or "").split(".")
    if len(partes) != 3:
        raise EstadoInvalido("state malformado")
    tenant_bruto, carimbo, assinatura = partes

    esperado = _assinar(f"{tenant_bruto}.{carimbo}", conf)
    if not hmac.compare_digest(assinatura, esperado):
        raise EstadoInvalido("state com assinatura inválida")

    try:
        momento = int(carimbo)
    except ValueError as exc:
        raise EstadoInvalido("state com carimbo inválido") from exc

    if abs(time.time() - momento) > VALIDADE_ESTADO:
        raise EstadoInvalido("state expirado: refaça a autorização (a janela é de 15 minutos)")

    try:
        return uuid.UUID(tenant_bruto)
    except ValueError as exc:
        raise EstadoInvalido("state sem tenant válido") from exc


async def salvar(
    sessao: AsyncSession,
    tenant_id: uuid.UUID,
    token: TokenOAuth,
    *,
    sandbox: bool,
    settings: Settings | None = None,
) -> FreteCredencial:
    """Guarda (ou substitui) a credencial do tenant, com os tokens selados."""
    conf = settings or get_settings()
    cofre = _cofre(conf)
    aad = aad_do_tenant(tenant_id)

    existente = await por_tenant(sessao, tenant_id)
    credencial = existente or FreteCredencial(tenant_id=tenant_id)

    credencial.access_token_selado = cofre.selar(token.access_token.encode(), aad=aad)
    if token.refresh_token:
        credencial.refresh_token_selado = cofre.selar(token.refresh_token.encode(), aad=aad)
    credencial.expira_em = token.expira_em
    credencial.escopo = token.escopo
    credencial.sandbox = sandbox
    credencial.ativo = True
    credencial.renovado_em = datetime.now(UTC)

    if existente is None:
        sessao.add(credencial)
    await sessao.flush()
    return credencial


async def por_tenant(sessao: AsyncSession, tenant_id: uuid.UUID) -> FreteCredencial | None:
    resultado = await sessao.execute(
        select(FreteCredencial).where(FreteCredencial.tenant_id == tenant_id)
    )
    return resultado.scalars().first()


async def revogar(sessao: AsyncSession, tenant_id: uuid.UUID) -> bool:
    """Marca como inativa e apaga os tokens selados."""
    credencial = await por_tenant(sessao, tenant_id)
    if credencial is None:
        return False
    credencial.ativo = False
    credencial.access_token_selado = b""
    credencial.refresh_token_selado = None
    credencial.expira_em = None
    await sessao.flush()
    return True


def trocar_codigo_por_token(
    code: str, sandbox: bool, settings: Settings | None = None
) -> TokenOAuth:
    """Troca o `code` do callback por tokens, usando as credenciais do app."""
    conf = settings or get_settings()
    if not conf.melhor_envio_client_id or not conf.melhor_envio_client_secret:
        raise ErroDeFrete(
            "MELHOR_ENVIO_CLIENT_ID e MELHOR_ENVIO_CLIENT_SECRET não configurados: "
            "sem eles não há como trocar o código por token"
        )
    return trocar_codigo(
        code=code,
        client_id=conf.melhor_envio_client_id,
        client_secret=conf.melhor_envio_client_secret,
        redirect_uri=conf.melhor_envio_redirect_uri,
        sandbox=sandbox,
    )


async def _token_valido(
    sessao: AsyncSession, credencial: FreteCredencial, settings: Settings
) -> TokenOAuth:
    """Devolve um token utilizável, renovando se estiver perto de vencer."""
    if not credencial.ativo:
        raise NaoAutorizado(
            "o Melhor Envio não está autorizado para este tenant; use GET /v1/fretes/oauth/iniciar"
        )

    cofre = _cofre(settings)
    aad = aad_do_tenant(credencial.tenant_id)
    access = cofre.abrir(credencial.access_token_selado, aad=aad).decode()

    token = TokenOAuth(
        access_token=access,
        refresh_token=None,
        expira_em=credencial.expira_em,
    )
    if not token.expirado:
        return token

    if not credencial.refresh_token_selado:
        raise NaoAutorizado(
            "o acesso ao Melhor Envio venceu e não há refresh_token: "
            "refaça a autorização em GET /v1/fretes/oauth/iniciar"
        )

    refresh = cofre.abrir(credencial.refresh_token_selado, aad=aad).decode()
    try:
        novo = renovar(
            refresh_token=refresh,
            client_id=settings.melhor_envio_client_id,
            client_secret=settings.melhor_envio_client_secret,
            sandbox=credencial.sandbox,
        )
    except (ErroDeAutorizacao, Exception) as exc:
        credencial.ativo = False
        await sessao.flush()
        raise NaoAutorizado(
            "não foi possível renovar o acesso ao Melhor Envio "
            f"({type(exc).__name__}); o lojista precisa autorizar de novo"
        ) from exc

    await salvar(sessao, credencial.tenant_id, novo, sandbox=credencial.sandbox, settings=settings)
    logger.info("melhor_envio_token_renovado", extra={"tenant": str(credencial.tenant_id)})
    return novo


async def cliente_para(
    sessao: AsyncSession, tenant_id: uuid.UUID, settings: Settings | None = None
) -> MelhorEnvioClient:
    """Cliente pronto para uso, com token válido (renovando se preciso)."""
    conf = settings or get_settings()
    credencial = await por_tenant(sessao, tenant_id)
    if credencial is None:
        raise NaoAutorizado(
            "este tenant ainda não autorizou o Melhor Envio; use GET /v1/fretes/oauth/iniciar"
        )
    token = await _token_valido(sessao, credencial, conf)
    return MelhorEnvioClient(token.access_token, sandbox=credencial.sandbox)
