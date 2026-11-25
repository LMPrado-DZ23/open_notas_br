"""Conector Brizu — atendimento/agendamento pago vira pedido de NFS-e.

Contrato de entrada::

    {
      "evento_id": "ag-9876",             # obrigatório
      "valor": 90.00,                      # obrigatório
      "servico": "Corte feminino",         # obrigatório (descrição do serviço)
      "competencia": "2026-11",            # opcional
      "cliente": {"nome": "...", "documento": "...", "email": "..."},  # opcional
      "agendamento_id": "AG-1"             # opcional
    }

Diferença em relação à DZ23: aqui o campo de descrição se chama `servico`, porque
é o vocabulário da plataforma de agendamento. O conector traduz; o serviço fiscal
não precisa saber disso.
"""

from __future__ import annotations

from typing import Any

from app.integrations.base import (
    ErroDeIntegracao,
    PedidoEmissao,
    exigir,
    para_decimal,
)


class ConectorBrizu:
    """Interpreta eventos de atendimento pago da Brizu."""

    nome = "brizu"

    def interpretar(self, payload: dict[str, Any]) -> PedidoEmissao:
        evento_id = exigir(payload, "evento_id", tipo=str)
        valor = para_decimal(exigir(payload, "valor"), "valor")
        if valor <= 0:
            raise ErroDeIntegracao("valor deve ser maior que zero")
        descricao = exigir(payload, "servico", tipo=str)

        cliente = payload.get("cliente") or {}
        if not isinstance(cliente, dict):
            raise ErroDeIntegracao("campo cliente deveria ser objeto")

        return PedidoEmissao(
            parceiro=self.nome,
            idempotency_key=f"brizu:{evento_id}",
            valor=valor,
            descricao=descricao,
            competencia=payload.get("competencia"),
            tomador_nome=cliente.get("nome"),
            tomador_documento=cliente.get("documento"),
            tomador_email=cliente.get("email"),
            referencia_externa=payload.get("agendamento_id"),
            origem_payload=payload,
        )
