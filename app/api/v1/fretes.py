"""Rotas de frete: autorização OAuth e cotação por carrinho.

Fluxo para o lojista:

1. `GET /v1/fretes/oauth/iniciar` devolve a URL do Melhor Envio;
2. ele autoriza no navegador e é redirecionado para o callback;
3. `GET /v1/fretes/oauth/callback` troca o código e guarda o token cifrado;
4. `POST /v1/fretes/cotacao` cota por CEP de destino + itens do carrinho.

O cálculo do frete é **somente leitura**: cota e devolve preço/prazo. Não compra
etiqueta — comprar gasta saldo da loja e exige o cliente já ter pago o frete.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import tenant_atual
from app.core.config import Settings, get_settings
from app.db.models.tenant import Tenant
from app.db.session import get_session
from app.frete import service as frete_service
from app.frete.client import ErroDeCotacao, Produto
from app.frete.constants import ESCOPOS_ETIQUETA
from app.frete.oauth import ErroMelhorEnvio, autorizacao_url

router = APIRouter(prefix="/fretes", tags=["frete"])


class AutorizacaoOut(BaseModel):
    url: str = Field(..., description="Abra esta URL no navegador para autorizar")
    expira_em_minutos: int = 15
    escopos: list[str]


class StatusOut(BaseModel):
    autorizado: bool
    sandbox: bool | None = None
    expira_em: str | None = None
    renovado_em: str | None = None
    escopo: str | None = None
    proximo_passo: str


class ItemCarrinho(BaseModel):
    peso_kg: Decimal = Field(..., gt=0, le=1000)
    altura_cm: Decimal = Field(..., gt=0, le=300)
    largura_cm: Decimal = Field(..., gt=0, le=300)
    comprimento_cm: Decimal = Field(..., gt=0, le=300)
    valor: Decimal = Field(..., ge=0)
    quantidade: int = Field(default=1, ge=1, le=999)


class CotacaoIn(BaseModel):
    cep_destino: str = Field(..., min_length=8, max_length=9, examples=["01001-000"])
    cep_origem: str | None = Field(
        default=None,
        min_length=8,
        max_length=9,
        description="Vazio usa o CEP da configuração fiscal do tenant.",
    )
    itens: list[ItemCarrinho] = Field(..., min_length=1, max_length=100)


class OpcaoOut(BaseModel):
    servico_id: int
    transportadora: str
    servico: str
    preco: Decimal
    prazo_dias: int
    moeda: str


class CotacaoOut(BaseModel):
    opcoes: list[OpcaoOut]
    mais_barata: OpcaoOut | None = None
    mais_rapida: OpcaoOut | None = None
    observacao: str


@router.get(
    "/oauth/iniciar",
    response_model=AutorizacaoOut,
    summary="URL para o lojista autorizar o Melhor Envio",
)
async def iniciar_autorizacao(
    tenant: Tenant = Depends(tenant_atual),
    settings: Settings = Depends(get_settings),
) -> AutorizacaoOut:
    if not settings.melhor_envio_client_id or not settings.melhor_envio_redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "integração do Melhor Envio não configurada: defina "
                "MELHOR_ENVIO_CLIENT_ID e MELHOR_ENVIO_REDIRECT_URI"
            ),
        )
    state = frete_service.gerar_estado(tenant.id, settings)
    url = autorizacao_url(
        client_id=settings.melhor_envio_client_id,
        redirect_uri=settings.melhor_envio_redirect_uri,
        state=state,
        sandbox=settings.melhor_envio_sandbox,
        escopos=ESCOPOS_ETIQUETA,
    )
    return AutorizacaoOut(
        url=url,
        expira_em_minutos=frete_service.VALIDADE_ESTADO // 60,
        escopos=list(ESCOPOS_ETIQUETA),
    )


@router.get(
    "/oauth/callback",
    response_model=StatusOut,
    summary="Callback do OAuth: troca o código e guarda o token cifrado",
    responses={
        400: {"description": "state inválido ou expirado"},
        502: {"description": "Melhor Envio recusou"},
    },
)
async def callback_oauth(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> StatusOut:
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"o lojista não autorizou ({error})",
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="code e state são obrigatórios"
        )

    try:
        tenant_id = frete_service.ler_estado(state, settings)
    except frete_service.EstadoInvalido as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        token = frete_service.trocar_codigo_por_token(code, settings.melhor_envio_sandbox, settings)
    except (frete_service.ErroDeFrete, ErroMelhorEnvio) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    credencial = await frete_service.salvar(
        db, tenant_id, token, sandbox=settings.melhor_envio_sandbox, settings=settings
    )
    await db.commit()
    return StatusOut(
        autorizado=True,
        sandbox=credencial.sandbox,
        expira_em=credencial.expira_em.isoformat() if credencial.expira_em else None,
        renovado_em=credencial.renovado_em.isoformat() if credencial.renovado_em else None,
        escopo=credencial.escopo,
        proximo_passo="pronto para cotar em POST /v1/fretes/cotacao",
    )


@router.get("/status", response_model=StatusOut, summary="Situação da autorização")
async def status_frete(
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> StatusOut:
    credencial = await frete_service.por_tenant(db, tenant.id)
    if credencial is None or not credencial.ativo:
        return StatusOut(
            autorizado=False,
            proximo_passo="use GET /v1/fretes/oauth/iniciar para autorizar",
        )
    vencido = credencial.expira_em is not None and credencial.expira_em <= _agora()
    return StatusOut(
        autorizado=not vencido or credencial.refresh_token_selado is not None,
        sandbox=credencial.sandbox,
        expira_em=credencial.expira_em.isoformat() if credencial.expira_em else None,
        renovado_em=credencial.renovado_em.isoformat() if credencial.renovado_em else None,
        escopo=credencial.escopo,
        proximo_passo=(
            "pronto para cotar"
            if not vencido
            else "acesso vencido: será renovado na próxima cotação"
        ),
    )


def _agora():
    from datetime import UTC, datetime

    return datetime.now(UTC)


@router.delete(
    "/credencial",
    status_code=status.HTTP_200_OK,
    summary="Revoga a autorização do Melhor Envio neste tenant",
)
async def revogar(
    tenant: Tenant = Depends(tenant_atual), db: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    apagou = await frete_service.revogar(db, tenant.id)
    await db.commit()
    return {
        "revogado": apagou,
        "observacao": (
            "os tokens foram apagados do nosso banco; para revogar também no Melhor "
            "Envio, remova o acesso no painel deles"
        ),
    }


@router.post(
    "/cotacao",
    response_model=CotacaoOut,
    summary="Calcula o frete do carrinho pelo CEP do cliente",
    responses={
        409: {"description": "Melhor Envio não autorizado para este tenant"},
        502: {"description": "Falha na cotação junto ao Melhor Envio"},
    },
)
async def cotar(
    dados: CotacaoIn,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CotacaoOut:
    cep_origem = dados.cep_origem or await _cep_da_config(db, tenant.id)
    if not cep_origem:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=("informe cep_origem ou cadastre o CEP na configuração fiscal do tenant"),
        )

    try:
        cliente = await frete_service.cliente_para(db, tenant.id, settings)
    except frete_service.NaoAutorizado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except frete_service.ErroDeFrete as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    produtos = [
        Produto(
            peso=i.peso_kg,
            altura=i.altura_cm,
            largura=i.largura_cm,
            comprimento=i.comprimento_cm,
            valor=i.valor,
            quantidade=i.quantidade,
        )
        for i in dados.itens
    ]

    try:
        cotacao = cliente.cotar(
            cep_origem=cep_origem, cep_destino=dados.cep_destino, produtos=produtos
        )
    except ErroDeCotacao as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    opcoes = [
        OpcaoOut(
            servico_id=o.servico_id,
            transportadora=o.transportadora,
            servico=o.servico,
            preco=o.preco,
            prazo_dias=o.prazo_dias,
            moeda=o.moeda,
        )
        for o in cotacao.disponiveis
    ]
    mais_barata = next((o for o in opcoes if _igual(o, cotacao.mais_barata)), None)
    mais_rapida = next((o for o in opcoes if _igual(o, cotacao.mais_rapida)), None)

    return CotacaoOut(
        opcoes=opcoes,
        mais_barata=mais_barata,
        mais_rapida=mais_rapida,
        observacao=(
            "cotação é somente leitura; a etiqueta é comprada à parte, depois que o "
            "cliente paga o frete. A compra usa o saldo da carteira do lojista."
        ),
    )


def _igual(opcao: OpcaoOut, referencia) -> bool:
    return referencia is not None and opcao.servico_id == referencia.servico_id


async def _cep_da_config(db: AsyncSession, tenant_id: uuid.UUID) -> str | None:
    """CEP de origem vem da configuração fiscal (o mesmo endereço do emitente)."""
    from sqlalchemy import select

    from app.db.models.tenant import TenantFiscalConfig

    resultado = await db.execute(
        select(TenantFiscalConfig)
        .where(TenantFiscalConfig.tenant_id == tenant_id)
        .order_by(TenantFiscalConfig.created_at)
    )
    config = resultado.scalars().first()
    if config is None:
        return None
    return (config.extra or {}).get("cep") if getattr(config, "extra", None) else None
