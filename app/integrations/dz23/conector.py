"""Conector DZ23 — venda/fatura paga vira pedido de NFS-e.

Contrato de entrada (o que a DZ23 envia)::

    {
      "evento_id": "venda-1234",          # obrigatório, único por evento
      "valor": 150.00,                     # obrigatório
      "descricao": "Corte + barba",        # obrigatório
      "competencia": "2026-11",            # opcional (padrão: mês corrente)
      "cliente": {"nome": "...", "documento": "...", "email": "..."},  # opcional
      "pedido_id": "PED-77"                # opcional, guardado como referência
    }

O `evento_id` é o que dá idempotência entre os dois sistemas: reenvio do mesmo
evento (webhook repetido, retry de rede) não gera segunda nota.
"""

from __future__ import annotations

from typing import Any

from app.integrations.base import (
    ErroDeIntegracao,
    PedidoEmissao,
    exigir,
    para_decimal,
)


class ConectorDz23:
    """Interpreta eventos de venda/fatura pagas da DZ23."""

    nome = "dz23"

    def interpretar(self, payload: dict[str, Any]) -> PedidoEmissao:
        evento_id = exigir(payload, "evento_id", tipo=str)
        valor = para_decimal(exigir(payload, "valor"), "valor")
        if valor <= 0:
            raise ErroDeIntegracao("valor deve ser maior que zero")
        descricao = exigir(payload, "descricao", tipo=str)

        cliente = payload.get("cliente") or {}
        if not isinstance(cliente, dict):
            raise ErroDeIntegracao("campo cliente deveria ser objeto")

        return PedidoEmissao(
            parceiro=self.nome,
            idempotency_key=f"dz23:{evento_id}",
            valor=valor,
            descricao=descricao,
            competencia=payload.get("competencia"),
            tomador_nome=cliente.get("nome"),
            tomador_documento=cliente.get("documento"),
            tomador_email=cliente.get("email"),
            referencia_externa=payload.get("pedido_id"),
            origem_payload=payload,
        )
