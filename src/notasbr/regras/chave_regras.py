"""Regras da chave de acesso e da coerência entre a chave e o conteúdo do XML.

Esta é a família de regras de maior retorno: a chave amarra UF, CNPJ, modelo,
série, número, forma de emissão e código numérico. Divergência entre a chave e os
campos do documento é um dos erros mais comuns em XML remontado ou adulterado.
"""

from __future__ import annotations

from ..cadastros import apenas_digitos
from ..chave import AMBIENTES, TIPO_POR_MODELO, UFS, ChaveAcesso, calcular_dv
from .base import Contexto, regra

PREFIXO_ID = {"nfe": "NFe", "cte": "CTe"}


def _precisa_chave(ctx: Contexto, codigo: str) -> bool:
    """Porta de entrada das regras que dependem da chave decomposta."""
    if ctx.chave_parseada is None:
        ctx.pular(codigo, "chave de acesso ausente ou inválida")
        return False
    return True


@regra("CHAVE-FMT-001", "Chave com 44 dígitos numéricos", ("nfe", "cte"))
def formato(ctx: Contexto) -> None:
    if not ctx.chave:
        ctx.erro(
            "CHAVE-FMT-001",
            f"chave de acesso não encontrada (esperado Id com prefixo {PREFIXO_ID[ctx.tipo]!r} "
            "ou protocolo de autorização)",
            "",
        )
        return
    if len(ctx.chave) != 44 or apenas_digitos(ctx.chave) != ctx.chave:
        ctx.erro(
            "CHAVE-FMT-001",
            f"chave de acesso deve ter 44 dígitos; encontrado {ctx.chave!r}",
            "",
            chave=ctx.chave,
        )


@regra("CHAVE-DV-001", "Dígito verificador da chave confere", ("nfe", "cte"))
def digito_verificador(ctx: Contexto) -> None:
    if not ctx.chave or len(ctx.chave) != 44 or apenas_digitos(ctx.chave) != ctx.chave:
        ctx.pular("CHAVE-DV-001", "chave ausente ou com formato inválido")
        return
    esperado = calcular_dv(ctx.chave[:43])
    if esperado != ctx.chave[43]:
        ctx.erro(
            "CHAVE-DV-001",
            f"dígito verificador da chave é {ctx.chave[43]}, deveria ser {esperado}",
            "",
            informado=ctx.chave[43],
            calculado=esperado,
        )


@regra("CHAVE-UF-001", "Código de UF da chave existe", ("nfe", "cte"))
def uf_conhecida(ctx: Contexto) -> None:
    if not _precisa_chave(ctx, "CHAVE-UF-001"):
        return
    assert ctx.chave_parseada is not None
    if ctx.chave_parseada.c_uf not in UFS:
        ctx.erro(
            "CHAVE-UF-001",
            f"código de UF {ctx.chave_parseada.c_uf} da chave não é um código IBGE válido",
            "",
            c_uf=ctx.chave_parseada.c_uf,
        )


@regra("CHAVE-MOD-001", "Modelo da chave corresponde ao documento", ("nfe", "cte"))
def modelo(ctx: Contexto) -> None:
    if not _precisa_chave(ctx, "CHAVE-MOD-001"):
        return
    assert ctx.chave_parseada is not None
    tipo_da_chave = TIPO_POR_MODELO.get(ctx.chave_parseada.modelo)
    if tipo_da_chave is None:
        ctx.aviso(
            "CHAVE-MOD-001",
            f"modelo {ctx.chave_parseada.modelo} da chave não é um modelo fiscal conhecido",
            "",
            modelo=ctx.chave_parseada.modelo,
        )
    elif tipo_da_chave != ctx.tipo:
        ctx.erro(
            "CHAVE-MOD-001",
            f"chave é do modelo {ctx.chave_parseada.modelo} ({tipo_da_chave}), "
            f"mas o XML é {ctx.tipo}",
            "",
            modelo=ctx.chave_parseada.modelo,
        )


@regra("CHAVE-AMM-001", "Ano/mês da chave é possível", ("nfe", "cte"))
def ano_mes(ctx: Contexto) -> None:
    if not _precisa_chave(ctx, "CHAVE-AMM-001"):
        return
    assert ctx.chave_parseada is not None
    if not 1 <= ctx.chave_parseada.mes <= 12:
        ctx.erro(
            "CHAVE-AMM-001",
            f"mês {ctx.chave_parseada.mes:02d} da chave (AAMM={ctx.chave_parseada.aamm}) não existe",
            "",
            aamm=ctx.chave_parseada.aamm,
        )


@regra("CHAVE-ID-001", "Id do documento bate com a chave", ("nfe", "cte"))
def id_bate_com_chave(ctx: Contexto) -> None:
    if not ctx.chave:
        ctx.pular("CHAVE-ID-001", "chave ausente")
        return
    atributo_id = ctx.corpo.get("Id") or ""
    esperado = PREFIXO_ID[ctx.tipo] + ctx.chave
    if atributo_id != esperado:
        ctx.erro(
            "CHAVE-ID-001",
            f"Id do documento é {atributo_id!r}, esperado {esperado!r}",
            "",
            id=atributo_id,
            esperado=esperado,
        )


@regra("CHAVE-CDV-001", "cDV do ide bate com o DV da chave", ("nfe", "cte"))
def cdv(ctx: Contexto) -> None:
    if not ctx.chave or len(ctx.chave) != 44:
        ctx.pular("CHAVE-CDV-001", "chave ausente ou com formato inválido")
        return
    informado = ctx.txt("ide/cDV")
    if informado is None:
        return  # ausência já é reportada por OBRIG
    if informado != ctx.chave[43]:
        ctx.erro(
            "CHAVE-CDV-001",
            f"cDV do documento é {informado!r}, último dígito da chave é {ctx.chave[43]!r}",
            "ide/cDV",
            informado=informado,
            chave=ctx.chave[43],
        )


@regra("CHAVE-CONSIST-001", "Campos do ide conferem com a chave", ("nfe", "cte"))
def campos_conferem(ctx: Contexto) -> None:
    if not _precisa_chave(ctx, "CHAVE-CONSIST-001"):
        return
    assert ctx.chave_parseada is not None
    info: ChaveAcesso = ctx.chave_parseada

    def conferir(relativo: str, valor_xml: str | None, valor_chave: str) -> None:
        if valor_xml is None:
            return  # ausência tem regra própria
        if apenas_digitos(valor_xml).lstrip("0") != apenas_digitos(valor_chave).lstrip("0"):
            ctx.erro(
                "CHAVE-CONSIST-001",
                f"{relativo} no XML é {valor_xml!r}, mas a chave indica {valor_chave!r}",
                relativo,
                no_xml=valor_xml,
                na_chave=valor_chave,
            )

    conferir("ide/cUF", ctx.txt("ide/cUF"), info.c_uf)
    conferir("ide/mod", ctx.txt("ide/mod"), info.modelo)
    conferir("ide/serie", ctx.txt("ide/serie"), info.serie)
    conferir(
        "ide/nNF" if ctx.tipo == "nfe" else "ide/nCT",
        ctx.txt("ide/nNF" if ctx.tipo == "nfe" else "ide/nCT"),
        info.numero,
    )
    conferir("ide/tpEmis", ctx.txt("ide/tpEmis"), info.tp_emis)
    conferir(
        "ide/cNF" if ctx.tipo == "nfe" else "ide/cCT",
        ctx.txt("ide/cNF" if ctx.tipo == "nfe" else "ide/cCT"),
        info.c_nf,
    )


@regra("CHAVE-EMIT-001", "CNPJ/CPF do emitente confere com a chave", ("nfe", "cte"))
def emitente_na_chave(ctx: Contexto) -> None:
    if not _precisa_chave(ctx, "CHAVE-EMIT-001"):
        return
    assert ctx.chave_parseada is not None
    documento = ctx.txt("emit/CNPJ") or ctx.txt("emit/CPF")
    if documento is None:
        return  # OBRIG cobre ausência de CNPJ
    normalizado = apenas_digitos(documento).zfill(14)
    if normalizado != ctx.chave_parseada.cnpj:
        ctx.erro(
            "CHAVE-EMIT-001",
            f"documento do emitente ({documento}) não corresponde ao bloco de "
            f"14 dígitos da chave ({ctx.chave_parseada.cnpj})",
            "emit/CNPJ",
            no_xml=documento,
            na_chave=ctx.chave_parseada.cnpj,
        )


@regra("CHAVE-AMM-002", "AAMM da chave coerente com a data de emissão", ("nfe", "cte"))
def aamm_versus_data(ctx: Contexto) -> None:
    if not _precisa_chave(ctx, "CHAVE-AMM-002"):
        return
    assert ctx.chave_parseada is not None
    if ctx.chave_parseada.tp_emis != "1":
        ctx.pular("CHAVE-AMM-002", "emissão em contingência: AAMM pode divergir de dhEmi")
        return
    data = ctx.txt("ide/dhEmi")
    if not data or len(data) < 7:
        return
    try:
        ano, mes = int(data[0:4]), int(data[5:7])
    except ValueError:
        ctx.aviso("CHAVE-AMM-002", f"dhEmi {data!r} não está em formato reconhecível", "ide/dhEmi")
        return
    if (ano % 100, mes) != (ctx.chave_parseada.ano % 100, ctx.chave_parseada.mes):
        ctx.aviso(
            "CHAVE-AMM-002",
            f"dhEmi {ano:04d}-{mes:02d} difere do AAMM {ctx.chave_parseada.aamm} da chave; "
            "verifique emissão em outro fuso ou contingência",
            "ide/dhEmi",
            dhEmi=data,
            aamm=ctx.chave_parseada.aamm,
        )


@regra("PROT-001", "Protocolo de autorização corresponde ao documento", ("nfe", "cte"))
def protocolo(ctx: Contexto) -> None:
    no_protocolo = "protNFe/infProt" if ctx.tipo == "nfe" else "protCTe/infProt"
    campo = "chNFe" if ctx.tipo == "nfe" else "chCTe"
    protocolo_elem = ctx.elem_raiz(no_protocolo)
    if protocolo_elem is None:
        return  # documento sem protocolo: NFe assinada, ainda não autorizada
    chave_protocolo = ctx.txt_de(protocolo_elem, campo)
    if not ctx.chave:
        ctx.pular("PROT-001", "chave ausente")
        return
    if chave_protocolo != ctx.chave:
        ctx.erro_em(
            "PROT-001",
            f"{campo} do protocolo é {chave_protocolo!r}, diferente da chave do documento",
            protocolo_elem,
            no_protocolo=chave_protocolo,
            chave=ctx.chave,
        )


@regra("AMB-001", "Ambiente de emissão válido e coerente", ("nfe", "cte"))
def ambiente(ctx: Contexto) -> None:
    tp_amb = ctx.txt("ide/tpAmb")
    if tp_amb is None:
        return
    if tp_amb not in AMBIENTES:
        ctx.erro(
            "AMB-001",
            f"tpAmb {tp_amb!r} inválido; esperado 1 (produção) ou 2 (homologação)",
            "ide/tpAmb",
            tpAmb=tp_amb,
        )
        return
    no_protocolo = "protNFe/infProt" if ctx.tipo == "nfe" else "protCTe/infProt"
    protocolo_elem = ctx.elem_raiz(no_protocolo)
    if protocolo_elem is None:
        return
    tp_amb_protocolo = ctx.txt_de(protocolo_elem, "tpAmb")
    if tp_amb_protocolo and tp_amb_protocolo != tp_amb:
        ctx.erro(
            "AMB-001",
            f"tpAmb do documento ({tp_amb}) difere do tpAmb do protocolo ({tp_amb_protocolo})",
            "ide/tpAmb",
            documento=tp_amb,
            protocolo=tp_amb_protocolo,
        )
