"""Data/hora de emissão no formato que os leiautes fiscais exigem.

Os três geradores (NF-e, CT-e, MDF-e) escreviam o sufixo `-03:00` de forma independente do instante:
a NF-e convertia para UTC **e** rotulava `-03:00` (deslocando 3 h), enquanto CT-e e MDF-e formatavam
sem converter e rotulavam `-03:00` do mesmo jeito. Os dois erros produzem `dhEmi` diferente do instante
real — data fiscal errada, e rejeição na virada do dia.

Aqui a regra é única: converte para o fuso de Brasília e deixa o `isoformat` escrever o offset real.
Data **sem** fuso é tratada como já estando em Brasília, que é a convenção do projeto (ver
`app/nfse/constants.py`).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")


def dh_emi(valor: datetime) -> str:
    """`dhEmi` no fuso de Brasília, com o offset que o leiaute espera (`-03:00`)."""
    local = (
        valor.astimezone(FUSO_BRASILIA)
        if valor.tzinfo is not None
        else valor.replace(tzinfo=FUSO_BRASILIA)
    )
    return local.isoformat(timespec="seconds")


__all__ = ["FUSO_BRASILIA", "dh_emi"]
