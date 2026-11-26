"""Gera data/xsd_manifest.json a partir dos schemas versionados.

Uso:
    python -m scripts.gerar_manifesto_xsd            # mostra o diff
    python -m scripts.gerar_manifesto_xsd --apply    # grava
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.core.schemas import MANIFESTO_PADRAO, carregar_manifesto, gerar_manifesto

RAIZ_SCHEMAS = Path("tests/fixtures/schemas")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera o manifesto SHA-256 dos XSD.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="grava o manifesto (sem esta flag, só mostra o que mudaria)",
    )
    args = parser.parse_args(argv)

    novo = gerar_manifesto(RAIZ_SCHEMAS)
    atual = carregar_manifesto(MANIFESTO_PADRAO)

    adicionados = sorted(set(novo) - set(atual))
    removidos = sorted(set(atual) - set(novo))
    alterados = sorted(k for k in set(novo) & set(atual) if novo[k] != atual[k])

    print(
        f"schemas: {len(novo)} | novos: {len(adicionados)} | "
        f"removidos: {len(removidos)} | alterados: {len(alterados)}"
    )
    for rotulo, itens in (
        ("+ novo", adicionados),
        ("- removido", removidos),
        ("~ alterado", alterados),
    ):
        for item in itens[:10]:
            print(f"  {rotulo}: {item}")

    if not args.apply:
        print("\n(dry-run) use --apply para gravar")
        return 0

    MANIFESTO_PADRAO.parent.mkdir(parents=True, exist_ok=True)
    MANIFESTO_PADRAO.write_text(json.dumps(novo, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\ngravado em {MANIFESTO_PADRAO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
