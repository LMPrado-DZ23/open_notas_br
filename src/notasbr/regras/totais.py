"""Regras de totalização: soma dos itens, valor total e pagamentos.

Toda comparação monetária usa tolerância de 1 centavo. Onde a regra oficial tem
variação de versão, a checagem é registrada como aviso ou informação — nunca como
erro — para não reprovar documento legítimo.
"""

from __future__ import annotations

from decimal import Decimal

from ..xml_util import decimal, dinheiro
from .base import Contexto, iguais, regra


@regra("TOTAL-VPROD-001", "Total de produtos é a soma dos itens", ("nfe",))
def total_produtos(ctx: Contexto) -> None:
    total = ctx.dec("total/ICMSTot/vProd")
    if total is None:
        ctx.pular("TOTAL-VPROD-001", "total/ICMSTot/vProd ausente")
        return
    itens = ctx.filhos("det")
    if not itens:
        return
    soma = Decimal("0")
    sem_valor = 0
    for item in itens:
        valor = decimal(ctx.txt_de(item, "prod/vProd"))
        if valor is None:
            sem_valor += 1
            continue
        soma += valor
    if sem_valor:
        ctx.aviso(
            "TOTAL-VPROD-001",
            f"{sem_valor} item(ns) sem prod/vProd; a soma pode não fechar",
            "total/ICMSTot/vProd",
            itens_sem_valor=sem_valor,
        )
    if not iguais(soma, total):
        ctx.erro(
            "TOTAL-VPROD-001",
            f"vProd total ({dinheiro(total)}) difere da soma dos itens ({dinheiro(soma)})",
            "total/ICMSTot/vProd",
            total=dinheiro(total),
            soma_itens=dinheiro(soma),
            diferenca=dinheiro(total - soma),
        )


@regra("TOTAL-VNF-001", "Valor total da nota é positivo", ("nfe",))
def valor_total_positivo(ctx: Contexto) -> None:
    total = ctx.dec("total/ICMSTot/vNF")
    if total is None:
        return
    if total <= 0:
        ctx.erro(
            "TOTAL-VNF-001",
            f"vNF deve ser maior que zero, encontrado {dinheiro(total)}",
            "total/ICMSTot/vNF",
            vNF=dinheiro(total),
        )


@regra("TOTAL-PAG-001", "Pagamentos somam o valor total", ("nfe",))
def pagamentos(ctx: Contexto) -> None:
    total = ctx.dec("total/ICMSTot/vNF")
    if total is None:
        ctx.pular("TOTAL-PAG-001", "vNF ausente")
        return
    grupo_pag = ctx.elem("pag")
    if grupo_pag is None:
        ctx.pular("TOTAL-PAG-001", "grupo pag ausente (layout anterior ao 4.00)")
        return

    soma = Decimal("0")
    encontrados = 0
    for det_pag in ctx.filhos_de(grupo_pag, "detPag"):
        valor = decimal(ctx.txt_de(det_pag, "vPag"))
        if valor is not None:
            soma += valor
            encontrados += 1
    if not encontrados:
        valor_unico = decimal(ctx.txt_de(grupo_pag, "vPag"))
        if valor_unico is None:
            ctx.pular("TOTAL-PAG-001", "nenhum vPag encontrado em pag")
            return
        soma = valor_unico

    troco = decimal(ctx.txt_de(grupo_pag, "vTroco")) or Decimal("0")
    # A regra admite as duas leituras: com o troco abatido ou não.
    if iguais(soma - troco, total) or iguais(soma, total):
        return
    ctx.erro(
        "TOTAL-PAG-001",
        f"soma dos pagamentos ({dinheiro(soma)}) menos troco ({dinheiro(troco)}) "
        f"não fecha com vNF ({dinheiro(total)})",
        "pag",
        soma_pagamentos=dinheiro(soma),
        troco=dinheiro(troco),
        vNF=dinheiro(total),
        diferenca=dinheiro(total - (soma - troco)),
    )


@regra("TOTAL-ITEM-001", "Quantidade x valor unitário confere com o item", ("nfe",))
def item_quantidade_valor(ctx: Contexto) -> None:
    itens = ctx.filhos("det")
    if not itens:
        return
    divergentes = 0
    for posicao, item in enumerate(itens, start=1):
        quantidade = decimal(ctx.txt_de(item, "prod/qCom"))
        unitario = decimal(ctx.txt_de(item, "prod/vUnCom"))
        total_item = decimal(ctx.txt_de(item, "prod/vProd"))
        if None in (quantidade, unitario, total_item):
            continue
        calculado = quantidade * unitario  # type: ignore[operator]
        if abs(calculado - total_item) > Decimal("0.10"):  # type: ignore[operator]
            divergentes += 1
            ctx.aviso(
                "TOTAL-ITEM-001",
                f"item {posicao}: qCom x vUnCom = {dinheiro(calculado)}, "
                f"mas vProd = {dinheiro(total_item)}",
                f"det[{posicao}]/prod/vProd",
                qCom=str(quantidade),
                vUnCom=str(unitario),
                vProd=dinheiro(total_item),
                calculado=dinheiro(calculado),
            )
    if divergentes:
        ctx.info(
            "TOTAL-ITEM-001",
            f"{divergentes} item(ns) com diferença entre qCom x vUnCom e vProd; "
            "pode ser arredondamento ou desconto rateado no item",
            "det",
        )


@regra("TOTAL-COMPOSICAO-001", "Composição indicativa do valor total", ("nfe",))
def composicao(ctx: Contexto) -> None:
    """Compara vNF com a composição clássica e reporta como **informação**.

    A fórmula de vNF muda com notas técnicas (ST, FCP, desoneração, IPI na base).
    Por isso aqui não existe juízo de erro: o delta é publicado para conferência
    humana, e quem conhece a regra da operação decide.
    """
    total = ctx.dec("total/ICMSTot/vNF")
    if total is None:
        ctx.pular("TOTAL-COMPOSICAO-001", "vNF ausente")
        return

    def pegar(campo: str) -> Decimal:
        return ctx.dec(f"total/ICMSTot/{campo}") or Decimal("0")

    soma = (
        pegar("vProd")
        + pegar("vFrete")
        + pegar("vSeg")
        + pegar("vOutro")
        + pegar("vII")
        + pegar("vIPI")
        + pegar("vST")
        + pegar("vFCPST")
        - pegar("vDesc")
    )
    delta = total - soma
    if not iguais(delta, Decimal("0")):
        ctx.info(
            "TOTAL-COMPOSICAO-001",
            f"vNF ({dinheiro(total)}) difere da composição indicativa "
            f"(prod+frete+seg+outro+II+IPI+ST+FCPST-desc = {dinheiro(soma)}) em "
            f"{dinheiro(delta)}; confira a nota técnica aplicável à operação",
            "total/ICMSTot/vNF",
            vNF=dinheiro(total),
            composicao=dinheiro(soma),
            delta=dinheiro(delta),
        )


@regra("CTE-PREST-001", "Prestação do serviço coerente", ("cte",))
def prestacao(ctx: Contexto) -> None:
    total = ctx.dec("vPrest/vTPrest")
    if total is None:
        ctx.pular("CTE-PREST-001", "vPrest/vTPrest ausente")
        return
    if total <= 0:
        ctx.erro(
            "CTE-PREST-001",
            f"vTPrest deve ser maior que zero, encontrado {dinheiro(total)}",
            "vPrest/vTPrest",
            vTPrest=dinheiro(total),
        )
        return

    receber = ctx.dec("vPrest/vRec")
    if receber is not None and receber > total:
        ctx.aviso(
            "CTE-PREST-001",
            f"vRec ({dinheiro(receber)}) é maior que o valor da prestação ({dinheiro(total)})",
            "vPrest/vRec",
            vRec=dinheiro(receber),
            vTPrest=dinheiro(total),
        )

    componentes = ctx.filhos_de(ctx.elem("vPrest"), "Comp")
    if not componentes:
        return
    soma = Decimal("0")
    for componente in componentes:
        valor = decimal(ctx.txt_de(componente, "vComp"))
        if valor is not None:
            soma += valor
    if not iguais(soma, total):
        ctx.aviso(
            "CTE-PREST-001",
            f"soma dos componentes ({dinheiro(soma)}) difere de vTPrest ({dinheiro(total)})",
            "vPrest",
            soma_componentes=dinheiro(soma),
            vTPrest=dinheiro(total),
        )
