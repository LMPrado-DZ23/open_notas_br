"""Rotas publicas de autopreenchimento: CEP e CNPJ.

Sao as duas consultas que um checkout faz antes de emitir: o CEP preenche o
endereco (e alimenta o calculo de frete), o CNPJ preenche os dados do cliente e
traz o codigo IBGE do municipio — que a nota fiscal exige.

Nenhuma das duas grava nada: sao leitura com cache. Por isso aceitam qualquer
tenant autenticado, sem escopo especial.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.cep.service import CepInvalido, CepNaoEncontrado, Endereco, FonteIndisponivel, ServicoCep
from app.core.redis import obter_redis

router = APIRouter(tags=["consulta"])


class EnderecoOut(BaseModel):
    cep: str
    logradouro: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    municipio: str | None = None
    uf: str | None = None
    codigo_ibge: str | None = Field(
        default=None,
        description="Código IBGE do município — é o que a emissão da nota usa.",
    )
    fonte: str


@router.get(
    "/cep/{cep}",
    response_model=EnderecoOut,
    summary="Autopreenche endereço a partir do CEP",
    responses={
        422: {"description": "CEP com formato inválido"},
        404: {"description": "CEP não encontrado nas fontes públicas"},
        503: {"description": "Fontes públicas indisponíveis — preencha manualmente"},
    },
)
async def consultar_cep(cep: str) -> EnderecoOut:
    """Consulta ViaCEP e, se preciso, BrasilAPI. Resultado fica em cache."""
    servico = ServicoCep(obter_redis())
    try:
        endereco: Endereco = await servico.buscar(cep)
    except CepInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except CepNaoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FonteIndisponivel as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return EnderecoOut(**endereco.para_dict())
