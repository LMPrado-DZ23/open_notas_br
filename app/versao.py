"""Versão do serviço, derivada do pacote instalado.

Ler do `importlib.metadata` evita a divergência clássica entre `pyproject.toml` e
uma constante escrita à mão que ninguém lembra de atualizar.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from notasbr.versao import SCHEMA_RELATORIO

try:
    APP_VERSION: str = version("notasbr")
except PackageNotFoundError:  # rodando direto do código, sem instalar
    APP_VERSION = "0.0.0+local"

__all__ = ["APP_VERSION", "SCHEMA_RELATORIO"]
