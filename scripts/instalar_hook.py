"""Instala o hook `pre-commit` que roda as mesmas checagens do CI.

O hook vive em `.git/hooks/`, que **não** é versionado. Este script existe para que outro
desenvolvedor (ou outra máquina) reproduza o gate com um comando, em vez de descobrir pelo
CI vermelho.

Uso: python -m scripts.instalar_hook
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

CONTEUDO = """#!/bin/sh
# Gerado por scripts/instalar_hook.py — roda o mesmo que o CI roda.
exec python -m scripts.check_ci
"""


def raiz_do_repo() -> Path:
    saida = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(saida.stdout.strip())


def main() -> int:
    destino = raiz_do_repo() / ".git" / "hooks" / "pre-commit"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(CONTEUDO, encoding="utf-8")
    modo = destino.stat().st_mode
    destino.chmod(modo | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"hook instalado em {destino}")
    print("Para pular uma vez: git commit --no-verify")
    return 0


if __name__ == "__main__":
    if os.name == "nt":
        print("Windows: o hook roda via Git Bash; se falhar, use `python -m scripts.check_ci`.")
    sys.exit(main())
