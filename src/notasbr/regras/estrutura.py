"""Regras de estrutura: raiz, namespace, versão do layout e campos obrigatórios.

Isto **não** substitui a validação contra o XSD oficial. É um subconjunto
curado: garante que o documento tem a espinha dorsal esperada antes de as outras
regras tentarem ler valores.
"""

from __future__ import annotations

from ..xml_util import local, namespace
from .base import Contexto, exigir_texto, regra

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_CTE = "http://www.portalfiscal.inf.br/cte"

#: Versões de layout reconhecidas, por tipo. "4.00" é a vigente para NF-e e CT-e.
VERSOES_SUPORTADAS: dict[str, tuple[str, ...]] = {
    "nfe": ("4.00", "3.10", "2.00"),
    "cte": ("4.00", "3.00"),
}

#: Campos escalares obrigatórios por tipo, relativo ao corpo (infNFe/infCte).
OBRIGATORIOS: dict[str, tuple[str, ...]] = {
    "nfe": (
        "ide/cUF",
        "ide/cNF",
        "ide/natOp",
        "ide/mod",
        "ide/serie",
        "ide/nNF",
        "ide/dhEmi",
        "ide/tpNF",
        "ide/idDest",
        "ide/cMunFG",
        "ide/tpImp",
        "ide/tpEmis",
        "ide/cDV",
        "ide/tpAmb",
        "ide/finNFe",
        "ide/indFinal",
        "ide/indPres",
        "ide/procEmi",
        "emit/CNPJ",
        "total/ICMSTot/vNF",
    ),
    "cte": (
        "ide/cUF",
        "ide/cCT",
        "ide/CFOP",
        "ide/natOp",
        "ide/mod",
        "ide/serie",
        "ide/nCT",
        "ide/dhEmi",
        "ide/tpImp",
        "ide/tpEmis",
        "ide/cDV",
        "ide/tpAmb",
        "ide/tpCTe",
        "ide/procEmi",
        "ide/modal",
        "ide/tpServ",
        "emit/CNPJ",
        "vPrest/vTPrest",
    ),
}


@regra("DOC-NS-001", "Namespace do documento corresponde ao tipo", ("nfe", "cte"))
def namespace_correto(ctx: Contexto) -> None:
    esperado = NS_NFE if ctx.tipo == "nfe" else NS_CTE
    encontrado = namespace(ctx.raiz.tag)
    if encontrado != esperado:
        ctx.erro(
            "DOC-NS-001",
            f"namespace da raiz é {encontrado!r}, esperado {esperado!r}",
            "",
            encontrado=encontrado,
            esperado=esperado,
        )


@regra("DOC-VER-001", "Versão do layout presente e reconhecida", ("nfe", "cte"))
def versao_layout(ctx: Contexto) -> None:
    suportadas = VERSOES_SUPORTADAS[ctx.tipo]
    if ctx.versao_layout is None:
        ctx.erro("DOC-VER-001", "atributo versao ausente no documento", "")
        return
    if ctx.versao_layout not in suportadas:
        ctx.aviso(
            "DOC-VER-001",
            f"versão de layout {ctx.versao_layout} não está na lista conferida "
            f"({', '.join(suportadas)}); o resultado pode ter falso positivo",
            "",
            versao=ctx.versao_layout,
        )


@regra("DOC-ID-001", "Identificador do documento presente", ("nfe", "cte"))
def identificador(ctx: Contexto) -> None:
    prefixo_esperado = "NFe" if ctx.tipo == "nfe" else "CTe"
    atributo_id = ctx.corpo.get("Id")
    if not atributo_id:
        ctx.erro("DOC-ID-001", f"atributo Id ausente em {local(ctx.corpo.tag)}", "")
        return
    if not atributo_id.startswith(prefixo_esperado):
        ctx.aviso(
            "DOC-ID-001",
            f"Id {atributo_id!r} não começa com {prefixo_esperado!r}",
            "",
            id=atributo_id,
        )


@regra("DOC-OBRIG-001", "Campos escalares obrigatórios preenchidos", ("nfe", "cte"))
def campos_obrigatorios(ctx: Contexto) -> None:
    for caminho in OBRIGATORIOS[ctx.tipo]:
        exigir_texto(ctx, caminho)


@regra("DOC-ITENS-001", "Documento tem ao menos um item", ("nfe", "cte"))
def tem_itens(ctx: Contexto) -> None:
    if ctx.tipo == "nfe":
        itens = ctx.filhos("det")
        if not itens:
            ctx.erro("DOC-ITENS-001", "nenhum elemento det (item) encontrado", "det")
    else:
        if ctx.elem("infCTeNorm") is None:
            ctx.erro(
                "DOC-ITENS-001",
                "infCTeNorm ausente; o CT-e normal precisa deste grupo",
                "infCTeNorm",
            )


@regra("NFE-DET-001", "nItem sequencial começando em 1", ("nfe",))
def itens_sequenciais(ctx: Contexto) -> None:
    itens = ctx.filhos("det")
    if not itens:
        return
    esperado = 1
    for posicao, item in enumerate(itens, start=1):
        bruto = item.get("nItem")
        if bruto is None:
            ctx.erro(
                "NFE-DET-001",
                f"item na posição {posicao} sem atributo nItem",
                f"det[{posicao}]",
            )
            continue
        try:
            numero = int(bruto)
        except ValueError:
            ctx.erro(
                "NFE-DET-001",
                f"nItem {bruto!r} não é inteiro",
                f"det[{posicao}]",
                nItem=bruto,
            )
            continue
        if numero != esperado:
            ctx.erro(
                "NFE-DET-001",
                f"nItem fora de sequência: esperado {esperado}, encontrado {numero}",
                f"det[{posicao}]",
                esperado=esperado,
                encontrado=numero,
            )
        esperado += 1


@regra("NFE-DEST-001", "Destinatário presente quando exigido", ("nfe",))
def destinatario(ctx: Contexto) -> None:
    ind_final = ctx.txt("ide/indFinal")
    ind_ie_dest = ctx.txt("dest/indIEDest")
    tem_dest = ctx.elem("dest") is not None
    if ind_final == "1" and not tem_dest:
        # Consumidor final exige dest, salvo NFC-e de operação com não contribuinte
        # em algumas UF, por isso o aviso e não o erro.
        ctx.aviso(
            "NFE-DEST-001",
            "indFinal=1 (consumidor final) sem grupo dest; confira a regra da UF",
            "ide/indFinal",
        )
    if tem_dest and ind_ie_dest is None:
        ctx.erro(
            "NFE-DEST-001",
            "grupo dest presente sem indIEDest (obrigatório na NF-e 4.00)",
            "dest",
        )


@regra("CTE-TOMADOR-001", "Tomador do serviço identificado", ("cte",))
def tomador(ctx: Contexto) -> None:
    if ctx.elem("toma") is None and ctx.elem("rem") is None and ctx.elem("dest") is None:
        ctx.erro(
            "CTE-TOMADOR-001",
            "CT-e sem toma, rem e dest: não há como identificar o tomador",
            "",
        )
