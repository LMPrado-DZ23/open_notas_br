"""Monta o laudo de cálculo a partir de uma emissão.

Separa a **decisão de o que auditar** da rota HTTP: a rota só chama `da_emissao` e
`auditoria_service.registrar`. Assim o conteúdo do laudo é testável sem subir API.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from app.tax.auditoria import LaudoCalculo, TabelaConsultada


def _decimal(valor: Any) -> Decimal | None:
    if valor is None:
        return None
    try:
        return Decimal(str(valor))
    except (ArithmeticError, ValueError):
        return None


def da_emissao(
    *,
    emitente: Mapping[str, Any],
    tomador: Mapping[str, Any] | None,
    servico: Mapping[str, Any],
    resultado: Mapping[str, Any],
    data_emissao: date,
    trace_id: uuid.UUID | str | None = None,
    regras: tuple[str, ...] = (),
    tabelas: tuple[TabelaConsultada, ...] = (),
) -> LaudoCalculo:
    """Constrói o laudo a partir dos dados que já circulam na emissão.

    A entrada inclui **o que influencia o tributo** (município, regime, alíquota,
    base de cálculo) e não o payload inteiro: guardar campos irrelevantes polui a
    auditoria e aumenta a superfície de dado pessoal.

    `trace_id` usa o id da fatura, que é o elo entre laudo, documento e logs.
    """
    entrada = {
        "municipio_ibge": servico.get("municipio_ibge") or emitente.get("municipio_ibge"),
        "uf": emitente.get("uf"),
        "regime": emitente.get("regime") or emitente.get("op_simp_nac"),
        "codigo_tributacao_nacional": servico.get("codigo_tributacao_nacional"),
        "aliquota": _decimal(servico.get("aliquota")),
        "base_calculo": _decimal(servico.get("valor") or servico.get("base_calculo")),
        "tomador_pj": bool(tomador and tomador.get("documento")),
    }

    saida = {
        "valor_iss": _decimal(resultado.get("valor_iss")),
        "aliquota_aplicada": _decimal(resultado.get("aliquota")),
        "iss_retido": bool(resultado.get("iss_retido", False)),
    }

    return LaudoCalculo(
        entrada=entrada,
        saida=saida,
        regras=regras,
        tabelas=tabelas,
        data_emissao=data_emissao,
        trace_id=str(trace_id) if trace_id else None,
    )
