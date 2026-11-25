"""Rotas de simulação tributária (IBS/CBS).

Simulação é cálculo explícito, não emissão: nada aqui toca a SEFIN nem grava
documento. Serve para o parceiro conferir valor antes de pedir a nota.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import tenant_atual
from app.tax import classificacoes
from app.tax.rtc import (
    TABELA_ALIQUOTAS,
    BaseCalculoNfse,
    ErroCalculoTributario,
    aliquotas_do_ano,
    calcular_ibscbs,
)
from app.tax.schemas import (
    AliquotaOut,
    CatalogoOut,
    ClassificacaoOut,
    SimulacaoIn,
    SimulacaoOut,
)

HTTP_422 = 422

# A simulação é serviço do produto, não oráculo público: exige credencial.
router = APIRouter(tags=["tributacao"], dependencies=[Depends(tenant_atual)])


@router.get(
    "/tax/aliquotas",
    response_model=list[AliquotaOut],
    summary="Alíquotas de referência de IBS/CBS por ano",
)
async def listar_aliquotas() -> list[AliquotaOut]:
    return [
        AliquotaOut(
            ano=a.ano,
            cbs=str(a.cbs),
            ibs=str(a.ibs),
            ibs_uf=str(a.ibs_uf),
            ibs_mun=str(a.ibs_mun),
            fonte=a.fonte,
        )
        for a in sorted(TABELA_ALIQUOTAS.values(), key=lambda x: x.ano)
    ]


@router.post(
    "/tax/simular",
    response_model=SimulacaoOut,
    summary="Simula CBS e IBS de uma NFS-e com parâmetros explícitos",
    responses={422: {"description": "Parâmetro inválido ou base negativa"}},
)
async def simular(dados: SimulacaoIn) -> SimulacaoOut:
    base = BaseCalculoNfse(
        valor_servico=dados.valor_servico,
        desconto_incondicional=dados.desconto_incondicional,
        v_calc_ree_rep_res=dados.reembolso_repasse,
        v_calc_ded_red_ibscbs=dados.deducao_reducao,
        iss=dados.iss,
        pis=dados.pis,
        cofins=dados.cofins,
    )
    try:
        resultado = calcular_ibscbs(
            base,
            ano_fato_gerador=dados.ano_fato_gerador,
            aliquota_cbs=dados.aliquota_cbs,
            aliquota_ibs=dados.aliquota_ibs,
            mei=dados.mei,
            optante_pendente=dados.optante_pendente,
        )
    except ErroCalculoTributario as exc:
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc

    if not resultado.valido:
        raise HTTPException(
            status_code=HTTP_422,
            detail={"erros": resultado.erros, "base_calculo": resultado.to_dict()["base_calculo"]},
        )

    corpo = resultado.to_dict()
    return SimulacaoOut(
        base_calculo=str(corpo["base_calculo"]),
        ano_fato_gerador=resultado.ano_fato_gerador,
        aliquota_cbs=str(resultado.aliquota_cbs),
        aliquota_ibs=str(resultado.aliquota_ibs),
        valor_cbs=str(resultado.valor_cbs),
        valor_ibs=str(resultado.valor_ibs),
        valor_total=str(resultado.valor_total),
        fonte_aliquota=resultado.fonte_aliquota,
        aliquota_ibs_uf=str(resultado.aliquota_ibs_uf)
        if resultado.aliquota_ibs_uf is not None
        else None,
        aliquota_ibs_mun=str(resultado.aliquota_ibs_mun)
        if resultado.aliquota_ibs_mun is not None
        else None,
        valor_ibs_uf=str(resultado.valor_ibs_uf) if resultado.valor_ibs_uf is not None else None,
        valor_ibs_mun=str(resultado.valor_ibs_mun) if resultado.valor_ibs_mun is not None else None,
        valido=resultado.valido,
        avisos=resultado.avisos,
        erros=resultado.erros,
    )


@router.get(
    "/tax/aliquotas/{ano}",
    response_model=AliquotaOut,
    summary="Alíquota de referência de um ano específico",
)
async def aliquota_do_ano(ano: int) -> AliquotaOut:
    referencia = aliquotas_do_ano(ano)
    if referencia is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"não há alíquota de referência para {ano}; informe as alíquotas "
                "explicitamente em POST /v1/tax/simular"
            ),
        )
    return AliquotaOut(
        ano=referencia.ano,
        cbs=str(referencia.cbs),
        ibs=str(referencia.ibs),
        ibs_uf=str(referencia.ibs_uf),
        ibs_mun=str(referencia.ibs_mun),
        fonte=referencia.fonte,
    )


@router.get(
    "/tax/classificacoes",
    response_model=list[ClassificacaoOut],
    summary="Catálogo de classificação tributária do IBS/CBS (cClassTrib)",
)
async def listar_classificacoes(
    ano: int | None = Query(default=None, description="Filtra pela vigência do ano"),
    busca: str | None = Query(default=None, description="Trecho da descrição ou o código"),
    limite: int = Query(default=50, ge=1, le=200),
) -> list[ClassificacaoOut]:
    """O catálogo é **versionado**: o mesmo código tem descrições diferentes em
    anos diferentes. Informe `ano` para obter a versão vigente na competência."""
    quando = date(ano, 1, 1) if ano else None
    encontradas = (
        classificacoes.pesquisar(busca or "", quando=quando, limite=limite)
        if busca
        else list(classificacoes.vigentes_em(quando))[:limite]
        if quando
        else list(classificacoes.todas())[:limite]
    )
    return [ClassificacaoOut(**c.to_dict()) for c in encontradas]


@router.get(
    "/tax/classificacoes/catalogo",
    response_model=CatalogoOut,
    summary="Procedência e tamanho do catálogo de classificações",
)
async def catalogo_classificacoes() -> CatalogoOut:
    return CatalogoOut(**classificacoes.metadados())


@router.get(
    "/tax/classificacoes/{codigo}",
    response_model=ClassificacaoOut,
    summary="Consulta uma classificação pelo código",
)
async def obter_classificacao(
    codigo: str,
    ano: int | None = Query(default=None, description="Ano de vigência desejado"),
) -> ClassificacaoOut:
    achada = classificacoes.buscar(codigo, quando=date(ano, 1, 1) if ano else None)
    if achada is None:
        raise HTTPException(status_code=404, detail=f"classificação {codigo} não encontrada")
    return ClassificacaoOut(**achada.to_dict())
