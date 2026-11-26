"""Importa endpoints de SEFAZ de um arquivo JSON, com procedência obrigatória.

Uso:
    python -m scripts.importar_catalogo data/endpoints_sefaz.json           # dry-run
    python -m scripts.importar_catalogo data/endpoints_sefaz.json --aplicar

O arquivo é uma lista de objetos:

    {
      "uf": "GO",
      "ambiente": "2",
      "servico": "NFeAutorizacao",
      "url": "https://<endpoint real>",
      "versao_soap": "1.2",
      "versao_layout": "4.00",
      "fonte_url": "https://<onde isso está documentado>",
      "autorizador": "GO"
    }

**Nenhuma URL é fornecida por este repositório.** `fonte_url` é obrigatória e precisa ser
https: a importação recusa endpoint sem procedência, porque um endpoint inventado faz o
sistema emitir contra o lugar errado e o erro só aparece na recusa do autorizador.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.catalogo import (
    aplicar_endpoints_sefaz,
    planejar_endpoints_sefaz,
    validar_lote,
)
from app.db.session import dispose_engine, obter_sessionmaker


def carregar(caminho: Path) -> list[dict]:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    if not isinstance(bruto, list):
        raise SystemExit("o arquivo precisa ser uma lista JSON de objetos")
    return bruto


async def executar(caminho: Path, *, aplicar: bool) -> int:
    brutas = carregar(caminho)
    validas, erros = validar_lote(brutas)

    if erros:
        print(f"{len(erros)} linha(s) inválida(s):")
        for erro in erros:
            print(f"  - {erro}")

    async with obter_sessionmaker()() as sessao:
        plano = await planejar_endpoints_sefaz(sessao, validas)
        print(
            f"válidas={len(validas)} inserir={len(plano.inserir)} "
            f"atualizar={len(plano.atualizar)} inalterado={len(plano.inalterado)}"
        )
        if aplicar:
            await aplicar_endpoints_sefaz(sessao, plano, dry_run=False)
            await sessao.commit()
            print(f"gravado: {len(plano.inserir)} novo(s), {len(plano.atualizar)} atualizado(s)")
        else:
            print("dry-run: nada foi gravado. Use --aplicar para gravar.")
    await dispose_engine()

    # Linha inválida é erro de operação, não aviso: o endpoint que faltou não existe.
    return 1 if erros else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arquivo", type=Path)
    parser.add_argument("--aplicar", action="store_true", help="grava (padrão é dry-run)")
    args = parser.parse_args(argv)
    if not args.arquivo.is_file():
        print(f"arquivo não encontrado: {args.arquivo}", file=sys.stderr)
        return 2
    return asyncio.run(executar(args.arquivo, aplicar=args.aplicar))


if __name__ == "__main__":
    raise SystemExit(main())
