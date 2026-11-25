"""Interface de linha de comando.

Códigos de saída::

    0  aprovado (ou aprovado com avisos, sem --estrito)
    1  reprovado: existe ao menos um erro (ou aviso, com --estrito)
    2  falha de leitura: arquivo ilegível, XML inválido, documento não suportado
    3  erro de uso: argumento inválido, caminho inexistente
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

from .cadastros import cnpj_valido, cpf_valido, formatar_cnpj, formatar_cpf
from .chave import ChaveAcesso
from .erros import ChaveInvalida, NotaFiscalError
from .modelos import Relatorio, Severidade
from .regras import catalogo
from .versao import VERSAO

SAIDA_OK = 0
SAIDA_REPROVADO = 1
SAIDA_LEITURA = 2
SAIDA_USO = 3

_ROTULO = {
    Severidade.ERRO: "ERRO ",
    Severidade.AVISO: "AVISO",
    Severidade.INFO: "INFO ",
}


def _configurar_saida() -> None:
    """Força UTF-8 no stdout para não quebrar acentuação no console do Windows."""
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            with contextlib.suppress(ValueError, OSError):  # stream exótico
                fluxo.reconfigure(encoding="utf-8", errors="replace")


def _imprimir_relatorio(relatorio: Relatorio, *, verboso: bool) -> None:
    """Imprime o relatório em formato legível por humano."""
    d = relatorio.to_dict()
    documento = d["documento"]
    resumo = d["resumo"]

    titulo = relatorio.arquivo or "(memória)"
    print(f"\n{titulo}")
    cabecalho = [
        (relatorio.modelo or relatorio.tipo.upper()),
        f"layout {relatorio.versao_layout or '?'}",
    ]
    if relatorio.chave:
        try:
            cabecalho.append(ChaveAcesso.parse(relatorio.chave).formatada())
        except ChaveInvalida:
            # A chave existe no documento mas não fecha: o achado já explica.
            cabecalho.append(relatorio.chave)
    print("  " + " | ".join(cabecalho))

    if relatorio.ambiente:
        print(f"  ambiente: {relatorio.ambiente}")
    emitente = documento.get("emitente") or {}
    if emitente:
        partes = [str(emitente.get("nome", "?"))]
        if "cnpj" in emitente:
            partes.append(str(emitente["cnpj"]))
        elif "cpf" in emitente:
            partes.append(str(emitente["cpf"]))
        if emitente.get("uf"):
            partes.append(str(emitente["uf"]))
        print("  emitente: " + " | ".join(partes))
    if relatorio.valor_total:
        print(f"  valor total: {relatorio.valor_total}")

    situacao = resumo["situacao"].replace("_", " ").upper()
    print(
        f"  situação: {situacao} "
        f"({resumo['erros']} erro(s), {resumo['avisos']} aviso(s), "
        f"{resumo['informacoes']} info, {resumo['regras_avaliadas']} regra(s), "
        f"{resumo['regras_puladas']} pulada(s))"
    )

    for achado in d["achados"]:
        if not verboso and achado["severidade"] == Severidade.INFO.value:
            continue
        rotulo = _ROTULO[Severidade(achado["severidade"])]
        onde = f"  [{achado['caminho']}]" if achado.get("caminho") else ""
        print(f"  {rotulo} {achado['codigo']}: {achado['mensagem']}{onde}")

    for pulada in d["regras_puladas"]:
        if verboso:
            print(f"  --    {pulada['codigo']}: {pulada['motivo']}")

    if verboso:
        print("  limitações:")
        for limitacao in d["limitacoes"]:
            print(f"    - {limitacao}")


def _comando_auditar(args: argparse.Namespace) -> int:
    caminhos = [Path(c) for c in args.arquivos]
    inexistentes = [c for c in caminhos if not c.is_file()]
    if inexistentes:
        for caminho in inexistentes:
            print(f"erro: arquivo não encontrado: {caminho}", file=sys.stderr)
        return SAIDA_USO

    from .auditor import auditar_arquivo

    relatorios: list[Relatorio | None] = []
    codigo = SAIDA_OK
    for caminho in caminhos:
        try:
            relatorio = auditar_arquivo(caminho, limite_bytes=args.limite_bytes)
        except NotaFiscalError as exc:
            print(f"\n{caminho.name}", file=sys.stderr)
            print(f"  não auditado: {exc}", file=sys.stderr)
            relatorios.append(None)
            codigo = max(codigo, SAIDA_LEITURA)
            continue
        except OSError as exc:
            print(f"\n{caminho.name}", file=sys.stderr)
            print(f"  não foi possível ler o arquivo: {exc}", file=sys.stderr)
            relatorios.append(None)
            codigo = max(codigo, SAIDA_LEITURA)
            continue

        relatorios.append(relatorio)
        if not args.json:
            _imprimir_relatorio(relatorio, verboso=args.verboso)

        resumo = relatorio.resumo
        if resumo.erros or (args.estrito and resumo.avisos):
            codigo = max(codigo, SAIDA_REPROVADO)

    if args.json:
        validos = [r.to_dict() for r in relatorios if r is not None]
        if len(validos) == 1:
            corpo: object = validos[0]
        else:
            corpo = {
                "schema": "notasbr.lote/1",
                "versao_ferramenta": VERSAO,
                "total": len(validos),
                "nao_auditados": sum(1 for r in relatorios if r is None),
                "relatorios": validos,
            }
        print(json.dumps(corpo, ensure_ascii=False, indent=2))

    return codigo


def _comando_chave(args: argparse.Namespace) -> int:
    try:
        chave = ChaveAcesso.parse(args.valor)
    except ChaveInvalida as exc:
        print(f"chave inválida: {exc}", file=sys.stderr)
        return SAIDA_LEITURA
    if args.json:
        print(json.dumps(chave.to_dict(), ensure_ascii=False, indent=2))
        return SAIDA_OK
    dados = chave.to_dict()
    print(f"chave     {chave.formatada()}")
    print(f"UF        {dados['uf']} ({dados['c_uf']})")
    print(f"emissão   {dados['ano']:04d}-{dados['mes']:02d}")
    print(f"CNPJ      {formatar_cnpj(dados['cnpj'])}")
    print(f"modelo    {dados['modelo']} ({dados['modelo_nome']})")
    print(f"série     {dados['serie']}")
    print(f"número    {dados['numero']}")
    print(f"tpEmis    {dados['tp_emis']} ({dados['forma_emissao']})")
    print(f"cNF       {dados['c_nf']}")
    print(f"DV        {dados['dv']}")
    return SAIDA_OK


def _comando_cnpj(args: argparse.Namespace) -> int:
    ok = cnpj_valido(args.valor)
    print(("válido  " if ok else "inválido") + f"  {formatar_cnpj(args.valor)}")
    return SAIDA_OK if ok else SAIDA_REPROVADO


def _comando_cpf(args: argparse.Namespace) -> int:
    ok = cpf_valido(args.valor)
    print(("válido  " if ok else "inválido") + f"  {formatar_cpf(args.valor)}")
    return SAIDA_OK if ok else SAIDA_REPROVADO


def _comando_regras(args: argparse.Namespace) -> int:
    regras = catalogo()
    if args.json:
        print(json.dumps(regras, ensure_ascii=False, indent=2))
        return SAIDA_OK
    largura = max(len(r["codigo"]) for r in regras) if regras else 0
    for regra in regras:
        tipos = ",".join(regra["tipos"])
        print(f"{regra['codigo']:<{largura}}  {regra['descricao']}  [{tipos}]")
    print(f"\n{len(regras)} regra(s) registrada(s) — notasbr {VERSAO}")
    return SAIDA_OK


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="notasbr",
        description="Auditoria offline de NF-e, NFC-e e CT-e. Não acessa a SEFAZ.",
    )
    parser.add_argument("--version", action="version", version=f"notasbr {VERSAO}")
    sub = parser.add_subparsers(dest="comando", required=True)

    auditar = sub.add_parser("auditar", help="audita um ou mais arquivos XML")
    auditar.add_argument("arquivos", nargs="+", metavar="XML")
    auditar.add_argument("--json", action="store_true", help="imprime o relatório em JSON")
    auditar.add_argument("--estrito", action="store_true", help="aviso também reprova (saída 1)")
    auditar.add_argument(
        "--verboso", "-v", action="store_true", help="mostra info, puladas e limitações"
    )
    auditar.add_argument(
        "--limite-bytes",
        type=int,
        default=20 * 1024 * 1024,
        dest="limite_bytes",
        metavar="N",
        help="tamanho máximo do arquivo (padrão: 20 MiB)",
    )
    auditar.set_defaults(funcao=_comando_auditar)

    chave = sub.add_parser("chave", help="decompõe e valida uma chave de acesso")
    chave.add_argument("valor")
    chave.add_argument("--json", action="store_true")
    chave.set_defaults(funcao=_comando_chave)

    cnpj = sub.add_parser("cnpj", help="valida CNPJ pelo dígito verificador")
    cnpj.add_argument("valor")
    cnpj.set_defaults(funcao=_comando_cnpj)

    cpf = sub.add_parser("cpf", help="valida CPF pelo dígito verificador")
    cpf.add_argument("valor")
    cpf.set_defaults(funcao=_comando_cpf)

    regras = sub.add_parser("regras", help="lista o catálogo de regras")
    regras.add_argument("--json", action="store_true")
    regras.set_defaults(funcao=_comando_regras)

    return parser


def main(argv: list[str] | None = None) -> int:
    _configurar_saida()
    parser = construir_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.funcao(args))
    except KeyboardInterrupt:  # pragma: no cover - interação
        print("\ninterrompido", file=sys.stderr)
        return SAIDA_USO


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
