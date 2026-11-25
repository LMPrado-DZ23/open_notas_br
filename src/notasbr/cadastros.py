"""Validação de CNPJ e CPF pelo dígito verificador (módulo 11).

Suporta **CNPJ alfanumérico**, vigente para novas inscrições desde julho/2026:
12 posições alfanuméricas (0-9, A-Z) mais 2 dígitos verificadores numéricos.
A regra de valor do caractere é a oficial: ``valor = código ASCII - 48``, o que
mantém dígitos valendo o próprio algarismo e letras de A (17) a Z (42).
Referência: IN RFB nº 2.229/2024.

O CPF continua numérico.

Só confere a **forma** (posições e DV). Não consulta a Receita Federal e não
prova que o documento existe, está ativo ou pertence a quem apresenta.
"""

from __future__ import annotations

import re

_NAO_ALNUM = re.compile(r"[^0-9A-Za-z]")
_SO_DIGITOS = re.compile(r"\D")
_CNPJ_VALIDO = re.compile(r"^[0-9A-Z]{12}\d{2}$")

_PESOS_CNPJ_1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_CNPJ_2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_CPF_1 = (10, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_CPF_2 = (11, 10, 9, 8, 7, 6, 5, 4, 3, 2)


def apenas_digitos(valor: str | None) -> str:
    """Remove tudo que não é dígito. `None` vira string vazia."""
    if not valor:
        return ""
    return _SO_DIGITOS.sub("", valor)


def normalizar_cnpj(valor: str | None) -> str:
    """Remove máscara e passa para maiúsculas (CNPJ alfanumérico é caixa alta)."""
    if not valor:
        return ""
    return _NAO_ALNUM.sub("", valor).upper()


def normalizar_cpf(valor: str | None) -> str:
    """Remove máscara do CPF."""
    return apenas_digitos(valor)


def _valor_caractere(caractere: str) -> int:
    """Valor numérico de uma posição do CNPJ.

    ``ord(c) - 48``: '0'..'9' → 0..9; 'A' → 17; 'Z' → 42.
    """
    return ord(caractere) - 48


def _digito_mod11(digitos: str, pesos: tuple[int, ...]) -> str:
    """Calcula um DV módulo 11 com os pesos informados.

    Regra usada por CNPJ e CPF: resto < 2 resulta em 0, senão ``11 - resto``.
    """
    soma = sum(_valor_caractere(d) * p for d, p in zip(digitos, pesos, strict=True))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def dv_cnpj(base: str) -> str:
    """Devolve os 2 dígitos verificadores para uma base de 12 posições.

    A base pode conter letras (CNPJ alfanumérico); o DV é sempre numérico.
    """
    base = normalizar_cnpj(base)
    if len(base) != 12:
        raise ValueError(f"base de CNPJ deve ter 12 posições, recebeu {len(base)}")
    if not all(c.isdigit() or c.isalpha() for c in base):
        raise ValueError(f"base de CNPJ com caractere inválido: {base!r}")
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
    """True se tem 14 posições válidas, não é repetição e o DV confere.

    Aceita o formato numérico tradicional e o alfanumérico.
    """
    num = normalizar_cnpj(valor)
    if len(num) != 14:
        return False
    if not _CNPJ_VALIDO.match(num):
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


def cnpj_alfanumerico(valor: str | None) -> bool:
    """True se o CNPJ usa ao menos uma letra (formato novo)."""
    num = normalizar_cnpj(valor)
    return len(num) == 14 and not num.isdigit()


def documento_valido(valor: str | None) -> bool:
    """True se o valor é um CNPJ (14) ou CPF (11) com DV válido."""
    if not valor:
        return False
    cnpj = normalizar_cnpj(valor)
    if len(cnpj) == 14:
        return cnpj_valido(cnpj)
    cpf = apenas_digitos(valor)
    if len(cpf) == 11:
        return cpf_valido(cpf)
    return False


def formatar_cnpj(valor: str | None) -> str:
    """Formata 14 posições como ``00.000.000/0000-00``. Devolve o bruto se não couber."""
    num = normalizar_cnpj(valor)
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
    """Mascara um documento para log/relatório, mantendo os 2 últimos caracteres."""
    num = normalizar_cnpj(valor) or apenas_digitos(valor)
    if len(num) < 4:
        return "*" * len(num)
    return "*" * (len(num) - 2) + num[-2:]
