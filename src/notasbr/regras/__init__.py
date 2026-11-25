"""Catálogo de regras.

Importar este pacote **executa o registro**: cada módulo abaixo usa ``@regra`` para
se anunciar. Novos módulos de regra precisam ser importados aqui, senão nunca
rodam — falha silenciosa clássica em arquitetura de plugins por decorador.
"""

from __future__ import annotations

from typing import Any

from .base import REGRAS, Contexto, Regra, regra, regras_para

# Importa os módulos de regra pelo efeito colateral de registro.
from . import assinatura, chave_regras, estrutura, totais, tributos  # noqa: F401  isort:skip

__all__ = ["REGRAS", "Contexto", "Regra", "catalogo", "regra", "regras_para"]


def catalogo() -> list[dict[str, Any]]:
    """Lista o catálogo de regras em ordem de código, pronto para serializar."""
    return [
        {"codigo": r.codigo, "descricao": r.descricao, "tipos": list(r.tipos)}
        for r in sorted(REGRAS, key=lambda r: r.codigo)
    ]
