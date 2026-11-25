"""Representação impressa a partir de XML já autorizado.

Rota para quem **já emitiu** a NF-e em outro sistema e precisa do DANFE ou das
etiquetas de volume: recebe o XML autorizado, devolve o PDF. Não grava nada — não
é emissão, é representação.

Por que isso existe: parte dos parceiros emite a NF-e no ERP próprio e usa este
serviço apenas para o documento auxiliar e a logística. Obrigar a reemitir para
ter o PDF seria pior.

O formato pedido é validado contra o catálogo de representações: pedir um que não
existe devolve 422 com a lista dos disponíveis, nunca PDF incompleto.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile

from app.api.deps import tenant_atual
from app.danfe import ErroRepresentacao, disponiveis, obter
from app.danfe.nfe import Danfse, EtiquetasVolume, registrar_todas
from notasbr.erros import XmlInvalido

HTTP_413 = 413
HTTP_422 = 422
TAMANHO_MAXIMO_XML = 5 * 1024 * 1024

router = APIRouter(tags=["representacao"])
registrar_todas()


@router.get(
    "/representacoes",
    summary="Lista as representações impressas disponíveis",
)
async def listar_representacoes() -> list[dict[str, str]]:
    return [{"documento": t.documento, "formato": t.formato} for t in disponiveis()]


@router.post(
    "/representacoes",
    response_class=Response,
    summary="Gera DANFE ou etiquetas a partir do XML autorizado",
    responses={
        200: {"content": {"application/pdf": {}}, "description": "PDF da representação"},
        413: {"description": "XML maior que 5 MB"},
        422: {"description": "XML inválido ou representação inexistente"},
    },
)
async def gerar_representacao(
    arquivo: Annotated[UploadFile, File(description="XML autorizado (nfeProc ou NFe)")],
    formato: str = Query(
        default="danfe",
        description="danfe, danfe_simplificado, etiquetas (NF-e) ou danfse (NFS-e)",
    ),
    volumes: int | None = Query(
        default=None,
        ge=1,
        le=200,
        description="Quantidade de etiquetas. Sem isso, usa o transp/vol do XML.",
    ),
    _tenant=Depends(tenant_atual),
) -> Response:
    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAXIMO_XML:
        raise HTTPException(
            status_code=HTTP_413,
            detail=f"XML acima de {TAMANHO_MAXIMO_XML // (1024 * 1024)} MB",
        )
    if not conteudo.strip():
        raise HTTPException(status_code=HTTP_422, detail="arquivo vazio")

    # A etiqueta precisa da quantidade de volumes, que o catálogo não carrega.
    if formato == "etiquetas":
        representacao = EtiquetasVolume(quantidade_volumes=volumes)
    else:
        try:
            representacao = obter("nfe", formato) if formato != "danfse" else Danfse()
        except ErroRepresentacao as exc:
            raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc

    try:
        pdf = representacao.gerar(conteudo)
    except XmlInvalido as exc:
        raise HTTPException(status_code=HTTP_422, detail=f"XML inválido: {exc}") from exc
    except ErroRepresentacao as exc:
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc

    nome = f"{formato}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nome}"'},
    )
