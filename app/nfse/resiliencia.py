"""Registro de circuitos por serviço e execução protegida.

Um circuito por **chave** (`sefaz:52:autorizacao`, `municipio:5200258:emitir`). Circuito
global seria errado: a SEFAZ de GO cair não pode parar a emissão municipal de São Paulo.

`executar` classifica a exceção antes de contar: só falha transitória abre o circuito.
Rejeição fiscal definitiva **não** conta — o serviço está no ar e respondendo; abrir por
erro do nosso lado pararia de emitir sem motivo.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.core.circuit import CircuitBreaker, CircuitoAberto

T = TypeVar("T")

#: Falhas que justificam nova tentativa: rede, timeout, indisponibilidade.
TRANSITORIAS: tuple[type[BaseException], ...] = (
    asyncio.TimeoutError,
    TimeoutError,
    ConnectionError,
    OSError,
)


class RegistroCircuitos:
    """Mantém um `CircuitBreaker` por chave. Não é thread-safe por desenho: use um
    registro por processo, e o estado real de saúde vem do serviço, não daqui."""

    def __init__(
        self,
        *,
        limite_falhas: int = 5,
        espera_s: float = 30.0,
        janela_s: float = 60.0,
    ) -> None:
        self._limite = limite_falhas
        self._espera = espera_s
        self._janela = janela_s
        self._circuitos: dict[str, CircuitBreaker] = {}

    def obter(self, chave: str) -> CircuitBreaker:
        if chave not in self._circuitos:
            self._circuitos[chave] = CircuitBreaker(
                nome=chave,
                limite_falhas=self._limite,
                espera_s=self._espera,
                janela_s=self._janela,
            )
        return self._circuitos[chave]

    def estados(self) -> dict[str, str]:
        """Estado atual de cada circuito, para métrica/health."""
        return {chave: str(cb.estado) for chave, cb in self._circuitos.items()}

    def resetar(self, chave: str | None = None) -> None:
        if chave is None:
            for cb in self._circuitos.values():
                cb.resetar()
        else:
            self.obter(chave).resetar()


#: Registro único do processo. Existe para que a rota, o `emissao_service` e o health
#: vejam o **mesmo** estado de circuito: um registro por chamada nunca abriria circuito,
#: porque cada requisição começaria com zero falhas.
registro_padrao = RegistroCircuitos()


def chave_sefaz(uf: str, servico: str) -> str:
    return f"sefaz:{uf.upper()}:{servico}"


def chave_municipio(codigo_ibge: str, operacao: str) -> str:
    return f"municipio:{codigo_ibge}:{operacao}"


async def executar[T](
    registro: RegistroCircuitos,
    chave: str,
    acao: Callable[[], Awaitable[T]],
    *,
    erros_transitorios: tuple[type[BaseException], ...] = TRANSITORIAS,
) -> T:
    """Executa `acao` sob o circuito.

    Levanta `CircuitoAberto` **sem chamar** o serviço quando o circuito está aberto — é o
    ponto: quando a SEFAZ está fora, insistir queima timeout de worker e atrasa a fila
    inteira.
    """
    circuito = registro.obter(chave)
    if not circuito.permite():
        raise CircuitoAberto(circuito.retry_after_s())

    try:
        resultado = await acao()
    except erros_transitorios:
        circuito.registrar_falha()
        raise
    except BaseException:
        # Erro definitivo: não conta como falha do serviço. Propaga sem abrir.
        raise
    else:
        circuito.registrar_sucesso()
        return resultado
