"""Execução de tarefa com retry e queda para a DLQ.

Fecha a lacuna "DLQ integrada ao worker": antes, a DLQ existia e ninguém a alimentava.

Regras que este módulo garante:

- **Só falha transitória é retentada.** Rejeição fiscal definitiva vai direto para a DLQ
  com o motivo, sem gastar tentativa: retentar uma rejeição não muda o resultado e queima
  cota do autorizador.
- **Toda falha persistente vai para a DLQ**, nunca desaparece. É o ponto de existir DLQ.
- **Sucesso deixa rastro zero**: nada é gravado, para a tabela não virar log.
- O commit fica com quem chamou, como no resto do worker.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.worker import dlq as dlq_service

#: Exceções que justificam nova tentativa.
TRANSITORIAS: tuple[type[BaseException], ...] = (
    asyncio.TimeoutError,
    TimeoutError,
    ConnectionError,
    OSError,
)


@dataclass(frozen=True, slots=True)
class ResultadoTarefa:
    """O que aconteceu com a execução."""

    ok: bool
    tentativas: int
    #: Preenchido quando a tarefa caiu para a DLQ.
    dlq_id: uuid.UUID | None = None
    erro: str | None = None
    valor: Any = None


def _descrever(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


async def executar_com_dlq[T](
    sessao: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    fila: str,
    payload: dict[str, Any],
    tarefa: Callable[[], Awaitable[T]],
    tentativas: int = 3,
    trace_id: str | None = None,
    erros_transitorios: tuple[type[BaseException], ...] = TRANSITORIAS,
) -> ResultadoTarefa:
    """Executa `tarefa` com retry; persistindo na DLQ quando todas falharem.

    `tentativas` conta **execuções**, não repetições: `tentativas=3` significa até três
    chamadas.
    """
    if tentativas < 1:
        raise ValueError("tentativas deve ser >= 1")

    ultimo: BaseException | None = None
    executadas = 0

    for numero in range(1, tentativas + 1):
        executadas = numero
        try:
            valor = await tarefa()
        except erros_transitorios as exc:
            ultimo = exc
            continue
        except Exception as exc:  # erro definitivo: não retenta
            ultimo = exc
            break
        else:
            return ResultadoTarefa(ok=True, tentativas=executadas, valor=valor)

    assert ultimo is not None  # o laço só sai daqui com falha registrada
    item = await dlq_service.enfileirar(
        sessao,
        tenant_id=tenant_id,
        fila=fila,
        payload=payload,
        erro=_descrever(ultimo),
        trace_id=trace_id,
        tentativas=executadas,
    )
    return ResultadoTarefa(
        ok=False,
        tentativas=executadas,
        dlq_id=item.id,
        erro=_descrever(ultimo),
    )
