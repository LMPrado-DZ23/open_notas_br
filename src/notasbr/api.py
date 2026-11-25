"""API HTTP opcional (extra ``notasbr[api]``).

Suba com::

    uvicorn notasbr.api:app --reload

O núcleo da biblioteca não depende de FastAPI. Este módulo só é importado quando
alguém quer o serviço.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from .auditor import LIMITACOES_PADRAO, auditar_bytes
from .cadastros import cnpj_valido, cpf_valido, formatar_cnpj, formatar_cpf
from .chave import ChaveAcesso
from .erros import (
    ArquivoGrandeDemais,
    ChaveInvalida,
    DocumentoNaoSuportado,
    XmlInvalido,
)
from .regras import catalogo
from .versao import SCHEMA_RELATORIO, VERSAO

#: Códigos HTTP usados aqui. Mantidos como inteiros porque os nomes de constante
#: do Starlette estão em transição (426 -> CONTENT) e mudam entre versões.
HTTP_413 = 413  # Content Too Large
HTTP_422 = 422  # Unprocessable Content

DESCRICAO = """
Auditoria **offline** de NF-e, NFC-e e CT-e.

O serviço não acessa a SEFAZ e não emite documento fiscal: ele lê o XML recebido
e devolve, regra por regra, o que está inconsistente.

Limitações importantes estão em `GET /v1/limitacoes` — leia antes de tratar o
resultado como aprovação fiscal.
"""


def criar_app() -> FastAPI:
    """Cria a aplicação. Separado do módulo para facilitar teste e injeção."""
    app = FastAPI(
        title="notasbr",
        version=VERSAO,
        description=DESCRICAO,
        license_info={"name": "MIT"},
    )

    @app.get("/v1/saude", tags=["meta"], summary="Estado do serviço")
    def saude() -> dict[str, Any]:
        return {
            "ok": True,
            "versao": VERSAO,
            "schema_relatorio": SCHEMA_RELATORIO,
            "regras": len(catalogo()),
        }

    @app.get("/v1/regras", tags=["meta"], summary="Catálogo de regras")
    def regras() -> dict[str, Any]:
        return {"total": len(catalogo()), "regras": catalogo()}

    @app.get("/v1/limitacoes", tags=["meta"], summary="O que a auditoria não prova")
    def limitacoes() -> dict[str, Any]:
        return {"limitacoes": list(LIMITACOES_PADRAO)}

    @app.post("/v1/auditar", tags=["auditoria"], summary="Audita um XML enviado")
    async def auditar(
        arquivo: UploadFile,
        limite_bytes: int = Query(
            20 * 1024 * 1024,
            ge=1,
            le=200 * 1024 * 1024,
            description="Tamanho máximo aceito para o XML",
        ),
    ) -> JSONResponse:
        dados = await arquivo.read()
        if len(dados) > limite_bytes:
            raise HTTPException(
                status_code=HTTP_413,
                detail=f"arquivo tem {len(dados)} bytes, acima do limite de {limite_bytes}",
            )
        try:
            relatorio = auditar_bytes(dados, arquivo=arquivo.filename, limite_bytes=limite_bytes)
        except XmlInvalido as exc:
            raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc
        except DocumentoNaoSuportado as exc:
            raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc
        except ArquivoGrandeDemais as exc:
            raise HTTPException(status_code=HTTP_413, detail=str(exc)) from exc
        return JSONResponse(content=relatorio.to_dict())

    @app.get("/v1/chave/{valor}", tags=["consulta"], summary="Decompõe uma chave de acesso")
    def chave(valor: str) -> dict[str, Any]:
        try:
            return ChaveAcesso.parse(valor).to_dict()
        except ChaveInvalida as exc:
            raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc

    @app.get("/v1/cnpj/{valor}", tags=["consulta"], summary="Valida CNPJ")
    def cnpj(valor: str) -> dict[str, Any]:
        return {"valido": cnpj_valido(valor), "formatado": formatar_cnpj(valor)}

    @app.get("/v1/cpf/{valor}", tags=["consulta"], summary="Valida CPF")
    def cpf(valor: str) -> dict[str, Any]:
        return {"valido": cpf_valido(valor), "formatado": formatar_cpf(valor)}

    return app


app = criar_app()
