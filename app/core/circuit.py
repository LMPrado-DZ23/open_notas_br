"""Circuit breaker por UF/prefeitura.

Seção 1.3 do v10.0. Implementado sem dependência nova (`aiobreaker` exigiria ADR pela
R9 e não traz nada que 90 linhas não resolvam aqui).

Estados: `FECHADO` → `ABERTO` → `MEIO_ABERTO`.

- **FECHADO**: passa tudo. Conta falhas consecutivas.
- **ABERTO**: recusa sem chamar o serviço. É o ponto: quando a SEFAZ está fora, insistir
  queima timeout de worker e atrasa a fila inteira.
- **MEIO_ABERTO**: deixa passar **uma** tentativa. Sucesso fecha; falha reabre.

Só falha **transitória** conta (timeout, 5xx, serviço indisponível). Rejeição fiscal
definitiva — schema inválido, cStat de rejeição — **não** conta: o serviço está no ar e
respondendo; abrir o circuito por isso pararia de emitir por erro do nosso lado.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum


class Estado(StrEnum):
    FECHADO = "fechado"
    ABERTO = "aberto"
    MEIO_ABERTO = "meio_aberto"


class ErroTransitorio(Exception):
    """Falha que justifica nova tentativa (timeout, 5xx, indisponível)."""


class CircuitoAberto(Exception):
    """O circuito está aberto: nem tente, o serviço está fora."""

    def __init__(self, retry_after_s: float) -> None:
        super().__init__(f"circuito aberto; tente em {retry_after_s:.0f}s")
        self.retry_after_s = retry_after_s


@dataclass
class CircuitBreaker:
    """Um circuito por serviço/UF. Não compartilhe entre UFs."""

    nome: str
    limite_falhas: int = 5
    janela_s: float = 60.0
    espera_s: float = 30.0
    _estado: Estado = field(default=Estado.FECHADO, init=False)
    _falhas: int = field(default=0, init=False)
    _aberto_em: float = field(default=0.0, init=False)
    _relogio: Callable[[], float] = field(default=time.monotonic, init=False, repr=False)

    @property
    def estado(self) -> Estado:
        if self._estado is Estado.ABERTO and self._relogio() - self._aberto_em >= self.espera_s:
            self._estado = Estado.MEIO_ABERTO
        return self._estado

    def permite(self) -> bool:
        """Pode chamar? FECHADO sim; MEIO_ABERTO sim (uma); ABERTO não."""
        return self.estado is not Estado.ABERTO

    def retry_after_s(self) -> float:
        if self.estado is not Estado.ABERTO:
            return 0.0
        decorrido = self._relogio() - self._aberto_em
        return max(0.0, self.espera_s - decorrido)

    def registrar_sucesso(self) -> None:
        self._falhas = 0
        self._estado = Estado.FECHADO

    def registrar_falha(self) -> None:
        """Conta falha **transitória** e abre quando passa do limite."""
        self._falhas += 1
        if self._estado is Estado.MEIO_ABERTO or self._falhas >= self.limite_falhas:
            self._estado = Estado.ABERTO
            self._aberto_em = self._relogio()

    def resetar(self) -> None:
        """Volta ao início. Usado em teste e em comando admin de recuperação."""
        self._estado = Estado.FECHADO
        self._falhas = 0
        self._aberto_em = 0.0
