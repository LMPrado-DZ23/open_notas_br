"""Validação de CNPJ e CPF pelo dígito verificador (módulo 11).

Só confere a **forma** (quantidade de dígitos e DV). Não consulta a Receita
Federal e não prova que o documento existe ou está ativo.
"""

from __future__ import annotations

import re

_SO_DIGITOS = re.compile(r"\D")

_PESOS_CNPJ_1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_CNPJ_2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_CPF_1 = (10, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_CPF_2 = (11, 10, 9, 8, 7, 6, 5, 4, 3, 2)


def apenas_digitos(valor: str | None) -> str:
    """Remove tudo que não é dígito. `None` vira string vazia."""
    if not valor:
        return ""
    return _SO_DIGITOS.sub("", valor)


def _digito_mod11(digitos: str, pesos: tuple[int, ...]) -> str:
    """Calcula um DV módulo 11 com os pesos informados.

    Regra usada por CNPJ e CPF: resto < 2 resulta em 0, senão ``11 - resto``.
    """
    soma = sum(int(d) * p for d, p in zip(digitos, pesos, strict=True))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def dv_cnpj(base: str) -> str:
    """Devolve os 2 dígitos verificadores para uma base de 12 dígitos."""
    base = apenas_digitos(base)
    if len(base) != 12:
        raise ValueError(f"base de CNPJ deve ter 12 dígitos, recebeu {len(base)}")
    d1 = _digito_mod11(base, _PESOS_CNPJ_1)
    d2 = _digito_mod11(base + d1, _PESOS_CNPJ_2)
    return d1 + d2


def dv_cpf(base: str) -> str:
    """Devolve os 2 dígitos verificadores para uma base de 9 dígitos."""
    base = apenas_digitos(base)
    if len(base) != 9:
        raise ValueError(f"base de CPF deve ter 9 dígitos, recebeu {len(base)}")
    d1 = _digito_mod11(base, _PESOS_CPF_1)
    d2 = _digito_mod11(base + d1, _PESOS_CPF_2)
    return d1 + d2


def cnpj_valido(valor: str | None) -> bool:
    """True se `valor` tem 14 dígitos, não é repetição e o DV confere."""
    num = apenas_digitos(valor)
    if len(num) != 14:
        return False
    if len(set(num)) == 1:  # 00000000000000 e afins passam no cálculo, mas não existem
        return False
    return num[12:] == dv_cnpj(num[:12])


def cpf_valido(valor: str | None) -> bool:
    """True se `valor` tem 11 dígitos, não é repetição e o DV confere."""
    num = apenas_digitos(valor)
    if len(num) != 11:
        return False
    if len(set(num)) == 1:
        return False
    return num[9:] == dv_cpf(num[:9])


def documento_valido(valor: str | None) -> bool:
    """True se o valor é um CNPJ (14) ou CPF (11) com DV válido."""
    num = apenas_digitos(valor)
    if len(num) == 14:
        return cnpj_valido(num)
    if len(num) == 11:
        return cpf_valido(num)
    return False


def formatar_cnpj(valor: str | None) -> str:
    """Formata 14 dígitos como ``00.000.000/0000-00``. Devolve o bruto se não couber."""
    num = apenas_digitos(valor)
    if len(num) != 14:
        return num
    return f"{num[:2]}.{num[2:5]}.{num[5:8]}/{num[8:12]}-{num[12:]}"


def formatar_cpf(valor: str | None) -> str:
    """Formata 11 dígitos como ``000.000.000-00``. Devolve o bruto se não couber."""
    num = apenas_digitos(valor)
    if len(num) != 11:
        return num
    return f"{num[:3]}.{num[3:6]}.{num[6:9]}-{num[9:]}"


def mascarar(valor: str | None) -> str:
    """Mascara um documento para log/relatório: ``**.***.***/****-81``.

    Mantém apenas os 2 últimos dígitos, o suficiente para conferência humana sem
    expor o número inteiro.
    """
    num = apenas_digitos(valor)
    if len(num) < 4:
        return "*" * len(num)
    return "*" * (len(num) - 2) + num[-2:]
