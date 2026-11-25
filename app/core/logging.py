"""Logging estruturado em JSON.

Motivo de ser JSON: o serviço roda em container e o destino natural é agregador
de log. Texto livre com CNPJ e valores fiscais no meio é ruim de filtrar e pior
de auditar.

Regra de segurança: nada neste módulo formata conteúdo de certificado. O
`RedigirSegredos` existe para que, se algum campo sensível for passado por
engano, ele saia como `***` em vez de vazar para o disco.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

CAMPOS_SENSIVEIS = frozenset(
    {
        "senha",
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "master_encryption_key",
        "pfx",
        "p12",
        "certificado",
        "private_key",
        "authorization",
    }
)

_RESERVADOS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {
    "asctime",
    "message",
    "taskName",
}


def _redigir(chave: str, valor: Any) -> Any:
    if chave.lower() in CAMPOS_SENSIVEIS:
        return "***"
    if isinstance(valor, (dict, list, tuple, set)):
        return "***"
    if isinstance(valor, bytes):
        return f"<{len(valor)} bytes>"
    return valor


class FormatadorJSON(logging.Formatter):
    """Formata cada registro como uma linha JSON."""

    def format(self, record: logging.LogRecord) -> str:
        carga: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "nivel": record.levelname,
            "logger": record.name,
            "mensagem": record.getMessage(),
        }
        if record.exc_info:
            carga["excecao"] = self.formatException(record.exc_info)

        for chave, valor in record.__dict__.items():
            if chave in _RESERVADOS or chave.startswith("_"):
                continue
            carga[chave] = _redigir(chave, valor)

        return json.dumps(carga, ensure_ascii=False, default=str)


class FormatadorTexto(logging.Formatter):
    """Formato curto para desenvolvimento no terminal."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-8s %(name)s %(message)s",
            datefmt="%H:%M:%S",
        )


def configurar_logging(nivel: str = "INFO", *, json_output: bool = True) -> None:
    """Configura o logger raiz uma vez, de forma idempotente."""
    raiz = logging.getLogger()
    raiz.setLevel(nivel.upper())

    for manipulador in list(raiz.handlers):
        raiz.removeHandler(manipulador)

    destino = logging.StreamHandler(sys.stdout)
    destino.setFormatter(FormatadorJSON() if json_output else FormatadorTexto())
    raiz.addHandler(destino)

    # Bibliotecas que falam demais em DEBUG.
    for ruidoso in ("uvicorn.access", "sqlalchemy.engine.Engine", "asyncpg"):
        logging.getLogger(ruidoso).setLevel(max(logging.INFO, raiz.level))
