"""Regras tributárias: CFOP, NCM, CST/CSOSN e coerência com o regime (CRT).

Só entram aqui tabelas fechadas e estáveis. Classificação fiscal correta (qual
CST para qual operação) depende da operação e da legislação vigente: o notasbr
verifica **forma** e **coerência interna**, não substitui o contador.
"""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from ..xml_util import filhos, local
from .base import Contexto, regra

#: Primeiro dígito do CFOP -> sentido da operação.
SENTIDO_CFOP: dict[str, str] = {
    "1": "entrada",
    "2": "entrada",
    "3": "entrada",
    "5": "saida",
    "6": "saida",
    "7": "saida",
}

#: CST do ICMS válidos na NF-e.
CST_ICMS: frozenset[str] = frozenset(
    {"00", "10", "20", "30", "40", "41", "50", "51", "60", "70", "90"}
)

#: CSOSN válidos (Simples Nacional).
CSOSN: frozenset[str] = frozenset(
    {"101", "102", "103", "201", "202", "203", "300", "400", "500", "900"}
)

#: Código de Regime Tributário do emitente.
CRT: dict[str, str] = {
    "1": "Simples Nacional",
    "2": "Simples Nacional com excesso de sublimite",
    "3": "Regime Normal",
    "4": "MEI",
}

#: Regimes que usam CSOSN em vez de CST do ICMS.
CRT_USA_CSOSN: frozenset[str] = frozenset({"1", "2", "4"})

_SO_DIGITOS = re.compile(r"^\d+$")


@regra("TRIB-CFOP-001", "CFOP com 4 dígitos e primeiro dígito válido", ("nfe", "cte"))
def cfop_forma(ctx: Contexto) -> None:
    if ctx.tipo == "nfe":
        itens = ctx.filhos("det")
        if not itens:
            return
        pares = [
            (f"det[{posicao}]/prod/CFOP", ctx.txt_de(item, "prod/CFOP"))
            for posicao, item in enumerate(itens, start=1)
        ]
    else:
        pares = [("ide/CFOP", ctx.txt("ide/CFOP"))]

    for caminho, valor in pares:
        if valor is None:
            continue  # OBRIG cobre ausência nos campos obrigatórios
        if not _SO_DIGITOS.match(valor) or len(valor) != 4:
            ctx.erro(
                "TRIB-CFOP-001",
                f"CFOP {valor!r} não tem 4 dígitos numéricos",
                caminho,
                cfop=valor,
            )
            continue
        if valor[0] not in SENTIDO_CFOP:
            ctx.erro(
                "TRIB-CFOP-001",
                f"CFOP {valor} começa com {valor[0]!r}, que não é um grupo válido "
                "(1, 2, 3, 5, 6 ou 7)",
                caminho,
                cfop=valor,
            )


@regra("TRIB-CFOP-002", "CFOP coerente com o sentido da operação", ("nfe",))
def cfop_versus_tpnf(ctx: Contexto) -> None:
    tp_nf = ctx.txt("ide/tpNF")
    if tp_nf is None:
        return
    esperado = {"0": "entrada", "1": "saida"}.get(tp_nf)
    if esperado is None:
        ctx.aviso(
            "TRIB-CFOP-002",
            f"tpNF {tp_nf!r} inválido; esperado 0 (entrada) ou 1 (saída)",
            "ide/tpNF",
            tpNF=tp_nf,
        )
        return
    for posicao, item in enumerate(ctx.filhos("det"), start=1):
        cfop = ctx.txt_de(item, "prod/CFOP")
        if not cfop or len(cfop) != 4:
            continue
        sentido = SENTIDO_CFOP.get(cfop[0])
        if sentido and sentido != esperado:
            ctx.erro(
                "TRIB-CFOP-002",
                f"item {posicao}: CFOP {cfop} é de {sentido}, mas tpNF indica "
                f"operação de {esperado}",
                f"det[{posicao}]/prod/CFOP",
                cfop=cfop,
                sentido_cfop=sentido,
                tpNF=tp_nf,
            )


@regra("TRIB-NCM-001", "NCM com 8 dígitos", ("nfe",))
def ncm(ctx: Contexto) -> None:
    for posicao, item in enumerate(ctx.filhos("det"), start=1):
        valor = ctx.txt_de(item, "prod/NCM")
        if valor is None:
            ctx.aviso(
                "TRIB-NCM-001",
                f"item {posicao} sem NCM",
                f"det[{posicao}]/prod/NCM",
            )
            continue
        if not _SO_DIGITOS.match(valor) or len(valor) != 8:
            ctx.aviso(
                "TRIB-NCM-001",
                f"item {posicao}: NCM {valor!r} não tem 8 dígitos",
                f"det[{posicao}]/prod/NCM",
                ncm=valor,
            )


def _grupo_icms(ctx: Contexto, item: ET.Element) -> ET.Element | None:
    """Devolve o grupo concreto de ICMS (ICMS00, ICMSSN102, ...) do item."""
    icms = None
    imposto = None
    for filho in item:
        if local(filho.tag) == "imposto":
            imposto = filho
            break
    if imposto is None:
        return None
    for filho in filhos(imposto, "ICMS"):
        for concreto in filho:
            if local(concreto.tag).startswith("ICMS"):
                icms = concreto
                break
    return icms


@regra("TRIB-ICMS-001", "ICMS presente com CST ou CSOSN conhecido", ("nfe",))
def icms_cst(ctx: Contexto) -> None:
    itens = ctx.filhos("det")
    if not itens:
        return
    for posicao, item in enumerate(itens, start=1):
        grupo = _grupo_icms(ctx, item)
        caminho_base = f"det[{posicao}]/imposto/ICMS"
        if grupo is None:
            ctx.erro(
                "TRIB-ICMS-001",
                f"item {posicao} sem grupo de ICMS",
                caminho_base,
            )
            continue
        nome = local(getattr(grupo, "tag", ""))
        cst = None
        csosn = None
        for filho in grupo:
            if local(filho.tag) == "CST":
                cst = (filho.text or "").strip()
            elif local(filho.tag) == "CSOSN":
                csosn = (filho.text or "").strip()
        if cst is None and csosn is None:
            ctx.erro(
                "TRIB-ICMS-001",
                f"item {posicao}: grupo {nome} sem CST nem CSOSN",
                f"{caminho_base}/{nome}",
            )
            continue
        if cst is not None and cst not in CST_ICMS:
            ctx.erro(
                "TRIB-ICMS-001",
                f"item {posicao}: CST {cst!r} não consta da tabela de CST do ICMS",
                f"{caminho_base}/{nome}/CST",
                cst=cst,
            )
        if csosn is not None and csosn not in CSOSN:
            ctx.erro(
                "TRIB-ICMS-001",
                f"item {posicao}: CSOSN {csosn!r} não consta da tabela de CSOSN",
                f"{caminho_base}/{nome}/CSOSN",
                csosn=csosn,
            )


@regra("TRIB-CRT-001", "Regime do emitente coerente com CST/CSOSN", ("nfe",))
def crt_versus_cst(ctx: Contexto) -> None:
    crt = ctx.txt("emit/CRT")
    if crt is None:
        ctx.pular("TRIB-CRT-001", "emit/CRT ausente na NF-e 4.00")
        return
    if crt not in CRT:
        ctx.erro(
            "TRIB-CRT-001",
            f"CRT {crt!r} inválido; esperado 1, 2, 3 ou 4",
            "emit/CRT",
            crt=crt,
        )
        return
    usa_csosn = crt in CRT_USA_CSOSN
    itens = ctx.filhos("det")
    for posicao, item in enumerate(itens, start=1):
        grupo = _grupo_icms(ctx, item)
        if grupo is None:
            continue
        nome = local(getattr(grupo, "tag", ""))
        tem_csosn = any(local(f.tag) == "CSOSN" for f in grupo)
        tem_cst = any(local(f.tag) == "CST" for f in grupo)
        if usa_csosn and tem_cst and not tem_csosn:
            ctx.aviso(
                "TRIB-CRT-001",
                f"item {posicao}: CRT {crt} ({CRT[crt]}) usa CSOSN, mas o grupo {nome} traz CST",
                f"det[{posicao}]/imposto/ICMS/{nome}",
                crt=crt,
                grupo=nome,
            )
        elif not usa_csosn and tem_csosn and not tem_cst:
            ctx.aviso(
                "TRIB-CRT-001",
                f"item {posicao}: CRT {crt} ({CRT[crt]}) usa CST, mas o grupo {nome} traz CSOSN",
                f"det[{posicao}]/imposto/ICMS/{nome}",
                crt=crt,
                grupo=nome,
            )


@regra("TRIB-PIS-COFINS-001", "Grupos de PIS e COFINS presentes", ("nfe",))
def pis_cofins(ctx: Contexto) -> None:
    itens = ctx.filhos("det")
    if not itens:
        return
    for posicao, item in enumerate(itens, start=1):
        imposto = None
        for filho in item:
            if local(filho.tag) == "imposto":
                imposto = filho
                break
        if imposto is None:
            ctx.erro("TRIB-PIS-COFINS-001", f"item {posicao} sem imposto", f"det[{posicao}]")
            continue
        for tributo in ("PIS", "COFINS"):
            if not filhos(imposto, tributo):
                ctx.aviso(
                    "TRIB-PIS-COFINS-001",
                    f"item {posicao} sem grupo {tributo}",
                    f"det[{posicao}]/imposto/{tributo}",
                )
