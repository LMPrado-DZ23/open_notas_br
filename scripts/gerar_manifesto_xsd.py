"""Gera data/xsd_manifest.json a partir dos schemas versionados.

Uso:
    python -m scripts.gerar_manifesto_xsd            # mostra o diff
    python -m scripts.gerar_manifesto_xsd --apply    # grava
    python -m scripts.gerar_manifesto_xsd --check    # falha (exit 1) se divergir — usado no gate
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
    # `--check` existe porque a verificação de integridade estava completa em `app/core/schemas.py`
    # mas **ninguém a chamava**: nem o app, nem o gate. Schema trocado passava despercebido — e de fato
    # o fixture da NFS-e estava adaptado (§82). Este modo é o que transforma a biblioteca em controle.
    parser.add_argument(
        "--check",
        action="store_true",
        help="não grava; sai 1 se o manifesto divergir do disco (uso em CI/gate)",
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

    if args.check:
        if adicionados or removidos or alterados:
            print(
                "\n[FALHOU] manifesto diverge: schemas trocados, removidos ou não registrados. "
                "Se a mudança é intencional, rode --apply e revise o diff do manifesto no commit."
            )
            return 1
        print(f"\n[OK] {len(novo)} schema(s) conferem com o manifesto")
        return 0

    if not args.apply:
        print("\n(dry-run) use --apply para gravar")
        return 0

    MANIFESTO_PADRAO.parent.mkdir(parents=True, exist_ok=True)
    MANIFESTO_PADRAO.write_text(json.dumps(novo, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\ngravado em {MANIFESTO_PADRAO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
