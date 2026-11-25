"""Contrato comum dos conectores de parceiro.

Um conector recebe o payload do parceiro e devolve um pedido de emissão
normalizado. Nada além disso: quem emite é o serviço fiscal, com a mesma
idempotência, o mesmo certificado e o mesmo registro.

Regra de idempotência entre sistemas: a `idempotency_key` é derivada do
identificador do evento no parceiro, com prefixo do parceiro. Assim, webhook
repetido do parceiro (que acontece) cai no caminho "já existe" em vez de emitir
nota nova.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable


class ErroDeIntegracao(Exception):
    """Payload do parceiro inválido ou incompleto."""


class EventoJaProcessado(ErroDeIntegracao):
    """O evento já virou nota. Não é erro de payload: é repetição."""


@dataclass(slots=True)
class PedidoEmissao:
    """Pedido normalizado, pronto para o serviço fiscal."""

    parceiro: str
    idempotency_key: str
    valor: Decimal
    descricao: str
    competencia: str | None = None
    tomador_nome: str | None = None
    tomador_documento: str | None = None
    tomador_email: str | None = None
    referencia_externa: str | None = None
    #: Payload original, guardado para auditoria e para reprocessamento.
    origem_payload: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ConectorDeParceiro(Protocol):
    """Contrato de um conector."""

    nome: str

    def interpretar(self, payload: dict[str, Any]) -> PedidoEmissao: ...


def exigir(payload: dict[str, Any], campo: str, *, tipo: type | None = None) -> Any:
    """Lê um campo obrigatório, com mensagem que diz qual parceiro e qual campo."""
    if campo not in payload or payload[campo] in (None, ""):
        raise ErroDeIntegracao(f"campo obrigatório ausente: {campo}")
    valor = payload[campo]
    if tipo is not None and not isinstance(valor, tipo):
        raise ErroDeIntegracao(
            f"campo {campo} deveria ser {tipo.__name__}; recebeu {type(valor).__name__}"
        )
    return valor


def para_decimal(valor: Any, campo: str) -> Decimal:
    """Converte valor monetário aceitando número ou string com vírgula."""
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, int | float):
        return Decimal(str(valor))
    if isinstance(valor, str):
        texto = valor.strip().replace("R$", "").replace(" ", "")
        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        elif "," in texto:
            texto = texto.replace(",", ".")
        try:
            return Decimal(texto)
        except Exception as exc:
            raise ErroDeIntegracao(f"campo {campo} não é valor monetário: {valor!r}") from exc
    raise ErroDeIntegracao(f"campo {campo} não é valor monetário: {valor!r}")
