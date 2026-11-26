"""Roda localmente o que o CI roda, antes do commit.

Existe por um motivo concreto: o CI ficou vermelho **duas vezes** por verificações que eu
esqueci de rodar (`gh run` nunca consultado; `ruff format --check` nunca executado). O
problema não era o código, era a verificação incompleta. Automatizar é a correção.

Uso:
    python -m scripts.check_ci          # rápido: lint + format + contrato
    python -m scripts.check_ci --tudo   # inclui a suíte completa

Código de saída 0 só quando todas as checagens passam.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Checagem:
    nome: str
    comando: list[str]
    rapida: bool = True


CHECAGENS: tuple[Checagem, ...] = (
    Checagem("lint", [sys.executable, "-m", "ruff", "check", "."]),
    Checagem("formatacao", [sys.executable, "-m", "ruff", "format", "--check", "."]),
    Checagem(
        "contrato openapi",
        [sys.executable, "-m", "pytest", "tests/test_openapi_sincronizado.py", "-q"],
    ),
    Checagem(
        "schema da DPS",
        [sys.executable, "-m", "pytest", "tests/test_schema_dps.py", "-q"],
    ),
    # `alembic check` responde "as migrations reproduzem os modelos?". Ficou fora por tempo
    # demais: o drift de defaults e do índice de `frete_credenciais` sobreviveu até a auditoria
    # §24 justamente porque nenhum gate olhava para isso.
    Checagem(
        "migrations reproduzem os modelos",
        [sys.executable, "-m", "alembic", "check"],
        rapida=False,
    ),
    Checagem(
        "suite completa",
        [sys.executable, "-m", "pytest", "-q"],
        rapida=False,
    ),
)


def rodar(checagens: tuple[Checagem, ...]) -> int:
    falhas: list[str] = []
    for checagem in checagens:
        executavel = shutil.which(checagem.comando[0]) or checagem.comando[0]
        comando = [executavel, *checagem.comando[1:]]
        print(f"[..] {checagem.nome}", flush=True)
        resultado = subprocess.run(comando, check=False)
        if resultado.returncode == 0:
            print(f"[OK] {checagem.nome}", flush=True)
        else:
            print(f"[FALHOU] {checagem.nome}", flush=True)
            falhas.append(checagem.nome)

    if falhas:
        print(f"\n{len(falhas)} checagem(ns) falharam: {', '.join(falhas)}")
        print("Corrija antes de commitar — o CI reprova exatamente estas.")
        return 1
    print("\nTodas as checagens passaram.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tudo",
        action="store_true",
        help="inclui a suíte completa (lento); padrão é só o que quebra antes",
    )
    args = parser.parse_args(argv)
    checagens = CHECAGENS if args.tudo else tuple(c for c in CHECAGENS if c.rapida)
    return rodar(checagens)


if __name__ == "__main__":
    raise SystemExit(main())
