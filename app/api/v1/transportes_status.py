"""Consulta de status de CT-e e MDF-e por UF, usando o catálogo de endpoints.

Complementa as rotas de geração: aqui o cliente pergunta ao autorizador se o serviço está no ar
**antes** de tentar emitir. Status é leitura — não autoriza documento.

A URL vem do catálogo (`webservices_sefaz`), nunca de literal no código: se o autorizador mudar
de endereço, muda o dado, não o código.
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, tenant_atual
from app.certificates import service as certificados
from app.core.config import Settings, get_settings
from app.cte import consulta as cte_consulta
from app.db.models.tenant import Tenant
from app.db.models.webservice_sefaz import ServicoSefaz, WebserviceSefaz
from app.mdfe import consulta as mdfe_consulta
from app.nfe.transporte import (
    ClienteSefaz,
    ErroSefazDefinitivo,
    ErroTransporte,
    RespostaSefaz,
    TransporteHTTP,
)
from app.nfse.injecao import executar_com_circuito
from app.nfse.resiliencia import registro_padrao

logger = logging.getLogger(__name__)

HTTP_422 = 422
HTTP_503 = 503
HTTP_504 = 504
router = APIRouter(prefix="/transportes", tags=["transporte"])

#: Modelo do documento e o serviço de status correspondente no catálogo.
_STATUS = {
    "cte": ("57", ServicoSefaz.CTE_STATUS),
    "mdfe": ("58", ServicoSefaz.MDFE_STATUS),
}


@router.get(
    "/status",
    summary="Consulta o status do serviço de CT-e ou MDF-e (não emite)",
    responses={
        200: {"description": "Retorno do autorizador, com cStat e motivo"},
        HTTP_422: {"description": "Certificado ausente ou parâmetro inválido"},
        HTTP_503: {"description": "Sem endpoint de status no catálogo para a UF"},
        HTTP_504: {"description": "Autorizador inacessível ou recusou de forma definitiva"},
    },
)
async def consultar_status_transporte(
    tenant: Annotated[Tenant, Depends(tenant_atual)],
    sessao: Annotated[AsyncSession, Depends(get_session)],
    conf: Annotated[Settings, Depends(get_settings)],
    documento: Annotated[Literal["cte", "mdfe"], Query(description="Documento")],
    uf: Annotated[str, Query(min_length=2, max_length=2, description="UF do autorizador")],
    ambiente: Annotated[Literal["1", "2"], Query(description="1 produção, 2 homologação")] = "2",
) -> dict[str, str | None]:
    modelo, servico = _STATUS[documento]

    url = await sessao.scalar(
        select(WebserviceSefaz.url).where(
            WebserviceSefaz.modelo == modelo,
            WebserviceSefaz.uf == uf.upper(),
            WebserviceSefaz.ambiente == ambiente,
            WebserviceSefaz.servico == servico,
        )
    )
    if url is None:
        # Catálogo incompleto é 503, não 422: não é erro do cliente, é serviço indisponível.
        raise HTTPException(
            status_code=HTTP_503,
            detail=(
                f"sem endpoint de status de {documento.upper()} para {uf.upper()} "
                f"no ambiente {ambiente}"
            ),
        )

    registro = await certificados.ativo(sessao, tenant.id)
    if registro is None:
        raise HTTPException(
            status_code=HTTP_422,
            detail=(
                "nenhum certificado A1 ativo para este tenant. "
                "Envie o .pfx em POST /v1/me/certificados."
            ),
        )
    certificado = await certificados.abrir_para_uso(
        sessao, registro, operacao="status_transporte", ambiente=ambiente, settings=conf
    )

    modulo = cte_consulta if documento == "cte" else mdfe_consulta
    transporte = TransporteHTTP(
        # `ssl_context()` já carrega o certificado de cliente e as raízes de confiança.
        # Não usar os PEM privados do cofre: a superfície pública existe para isto.
        ssl_context=certificado.ssl_context(),
        soap_action=modulo.ACAO,
        soap_versao=modulo.SOAP_VERSAO,
    )
    sefaz = ClienteSefaz(transporte, timeout_s=30.0)

    async def _consultar() -> RespostaSefaz:
        if documento == "cte":
            return await cte_consulta.consultar_status(
                sefaz, url=url, cuf=_cuf(uf), ambiente=ambiente
            )
        return await mdfe_consulta.consultar_status(sefaz, url=url, ambiente=ambiente)

    try:
        # Leitura também passa pelo circuito, escopada por **UF**: este endpoint recebe a UF do
        # autorizador, e a queda de GO não pode consumir timeout de SP. Antes, só as escritas
        # (emissão, cancelamento, evento) tinham circuito; a consulta queimava 30 s por requisição
        # enquanto a SEFAZ da UF estivesse fora (§85).
        resposta = await executar_com_circuito(
            registro_padrao, uf=uf.upper(), operacao="consulta_status", acao=_consultar
        )
    except ErroSefazDefinitivo as exc:
        raise HTTPException(status_code=HTTP_504, detail=str(exc)) from exc
    except ErroTransporte as exc:
        raise HTTPException(status_code=HTTP_504, detail=f"autorizador inacessível: {exc}") from exc

    logger.info(
        "status de transporte consultado",
        extra={
            "tenant_id": str(tenant.id),
            "documento": documento,
            "uf": uf,
            "cstat": resposta.cstat,
        },
    )
    return {
        "documento": documento,
        "uf": uf.upper(),
        "cstat": resposta.cstat,
        "motivo": resposta.texto("xMotivo"),
    }


def _cuf(uf: str) -> str:
    """Código IBGE da UF, reaproveitando a tabela que a NF-e já usa.

    Não duplicar: uma segunda tabela UF→código divergiria da primeira sem ninguém notar.
    """
    from app.nfe.base import ErroDeNFe, _codigo_uf

    try:
        return _codigo_uf(uf.upper())
    except (KeyError, ValueError, ErroDeNFe) as exc:
        raise HTTPException(status_code=HTTP_422, detail=f"UF desconhecida: {uf!r}") from exc
