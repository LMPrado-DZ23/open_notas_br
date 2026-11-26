"""Consulta de municípios atendidos (onboarding do cliente).

Rotas **públicas** (sem API key) de propósito: quem está integrando precisa saber quais
municípios existem e o que cada um exige **antes** de ter conta. Nada aqui é dado de
tenant, então não há o que vazar.

Não existe rota de escrita: município vem do seed do IBGE, não do cliente. Deixar um
tenant inventar município permitiria apontar emissão para código inexistente.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.municipio import MunicipioNFSe, ProvedorNFSe
from app.db.session import get_session

router = APIRouter(prefix="/municipios", tags=["municipios"])


def _serializar(municipio: MunicipioNFSe) -> dict:
    return {
        "codigo_ibge": municipio.codigo_ibge,
        "nome": municipio.nome,
        "uf": municipio.uf,
        "provedor": str(municipio.provedor),
        "versao_layout": municipio.versao_layout,
        "homologado": municipio.homologado,
        "exige_credencial_municipal": municipio.exige_credencial_municipal,
        "assina_rps": municipio.assina_rps,
        "assina_lote": municipio.assina_lote,
        "encoding": str(municipio.encoding),
        # `fonte_url` exposta: R3 exige origem rastreável, e o cliente tem o direito de
        # conferir de onde veio a configuração que vai emitir a nota dele.
        "fonte_url": municipio.fonte_url,
    }


@router.get("")
async def listar(
    uf: str | None = Query(default=None, min_length=2, max_length=2),
    nome: str | None = Query(default=None, min_length=2, max_length=60),
    provedor: ProvedorNFSe | None = None,
    homologado: bool | None = None,
    limite: int = Query(default=50, ge=1, le=200),
    deslocamento: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Lista paginada com filtros. `total` é o total do filtro, não da página."""
    filtros = []
    if uf:
        filtros.append(MunicipioNFSe.uf == uf.upper())
    if nome:
        # `ilike` sem acento não resolve "goiania" -> "Goiânia"; quem busca com acento
        # encontra. Documentado como limitação, não fingido como busca fuzzy.
        filtros.append(MunicipioNFSe.nome.ilike(f"{nome}%"))
    if provedor is not None:
        filtros.append(MunicipioNFSe.provedor == provedor)
    if homologado is not None:
        filtros.append(MunicipioNFSe.homologado == homologado)

    total = (
        await db.execute(select(func.count()).select_from(MunicipioNFSe).where(*filtros))
    ).scalar_one()

    consulta = (
        select(MunicipioNFSe)
        .where(*filtros)
        .order_by(MunicipioNFSe.uf, MunicipioNFSe.nome)
        .limit(limite)
        .offset(deslocamento)
    )
    municipios = (await db.execute(consulta)).scalars().all()
    return {
        "itens": [_serializar(m) for m in municipios],
        "total": total,
        "limite": limite,
        "deslocamento": deslocamento,
    }


@router.get("/{codigo_ibge}")
async def obter(codigo_ibge: str, db: AsyncSession = Depends(get_session)) -> dict:
    """Requisitos de emissão do município, para o cliente se preparar."""
    if len(codigo_ibge) != 7 or not codigo_ibge.isdigit():
        raise HTTPException(
            status_code=422,
            detail="código IBGE deve ter 7 dígitos",
        )
    municipio = (
        await db.execute(select(MunicipioNFSe).where(MunicipioNFSe.codigo_ibge == codigo_ibge))
    ).scalar_one_or_none()
    if municipio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="município não cadastrado"
        )
    return _serializar(municipio)
