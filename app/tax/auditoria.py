"""Auditoria de cálculo tributário: hash determinístico e rastro das regras.

Fatia 1 da Etapa C. Implementa o que dá para verificar **sem** banco: dado o mesmo
insumo e as mesmas tabelas, o resultado é idêntico e o hash é reprodutível.

Por que hash de entrada e de saída separados:

- **entrada**: prova que o cálculo usou exatamente aquele dado. Sem isso, um laudo
  fiscal não consegue demonstrar o que entrou.
- **saída**: prova que o resultado não foi alterado depois. É o que fecha a cadeia
  entre "o que o sistema calculou" e "o que foi para a nota".

O hash cobre números de forma **normalizada**: `Decimal("10.0")` e `Decimal("10.00")`
representam o mesmo valor tributário e não podem gerar hashes diferentes — senão o
teste de determinismo falharia por formatação, não por cálculo.

O que este módulo **não** faz: persistir. `CalculoAudit` como tabela, com retenção de
5 anos e consulta por `trace_id`, é a fatia 2.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

#: Versão do formato do laudo. Subir isto quando o conteúdo do rastro mudar, para
#: que laudos antigos continuem verificáveis pelo seu próprio formato.
VERSAO_FORMATO = 1


def _normalizar(valor: Any) -> Any:
    """Converte para JSON estável: decimal por string com 2 casas, data ISO."""
    if isinstance(valor, Decimal):
        return f"{valor.quantize(Decimal('0.01')):.2f}"
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, Mapping):
        return {str(k): _normalizar(v) for k, v in sorted(valor.items(), key=lambda i: str(i[0]))}
    if isinstance(valor, (list, tuple)):
        return [_normalizar(v) for v in valor]
    if isinstance(valor, bool) or valor is None:
        return valor
    if isinstance(valor, (int, float)):
        return valor
    return str(valor)


def hash_de(dados: Mapping[str, Any]) -> str:
    """SHA-256 do dicionário normalizado. Mesma entrada => mesmo hash, sempre."""
    canonico = json.dumps(
        _normalizar(dados), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TabelaConsultada:
    """Uma tabela de referência usada no cálculo, com a versão efetivamente lida."""

    nome: str
    versao: str
    vigencia_inicio: date | None = None
    vigencia_fim: date | None = None

    def para_dict(self) -> dict[str, Any]:
        return {
            "nome": self.nome,
            "versao": self.versao,
            "vigencia_inicio": self.vigencia_inicio,
            "vigencia_fim": self.vigencia_fim,
        }


@dataclass(frozen=True, slots=True)
class LaudoCalculo:
    """Rastro auditável de um cálculo. Imutável por construção."""

    entrada: Mapping[str, Any]
    saida: Mapping[str, Any]
    regras: tuple[str, ...] = ()
    tabelas: tuple[TabelaConsultada, ...] = ()
    data_emissao: date | None = None
    trace_id: str | None = None
    versao_formato: int = VERSAO_FORMATO
    extras: Mapping[str, Any] = field(default_factory=dict)

    @property
    def hash_entrada(self) -> str:
        return hash_de(self.entrada)

    @property
    def hash_saida(self) -> str:
        return hash_de(self.saida)

    @property
    def hash_laudo(self) -> str:
        """Cadeia completa: entrada + saída + regras + versões. É o que se arquiva."""
        return hash_de(
            {
                "versao_formato": self.versao_formato,
                "hash_entrada": self.hash_entrada,
                "hash_saida": self.hash_saida,
                "regras": list(self.regras),
                "tabelas": [t.para_dict() for t in self.tabelas],
                "data_emissao": self.data_emissao,
                "trace_id": self.trace_id,
            }
        )

    def para_dict(self) -> dict[str, Any]:
        """Serialização completa, incluindo os valores originais (não só os hashes)."""
        return {
            "versao_formato": self.versao_formato,
            "hash_entrada": self.hash_entrada,
            "hash_saida": self.hash_saida,
            "hash_laudo": self.hash_laudo,
            "entrada": _normalizar(self.entrada),
            "saida": _normalizar(self.saida),
            "regras": list(self.regras),
            "tabelas": [t.para_dict() for t in self.tabelas],
            "data_emissao": self.data_emissao.isoformat() if self.data_emissao else None,
            "trace_id": self.trace_id,
            "extras": _normalizar(dict(self.extras)),
        }


def tabela_vigente(tabelas: list[TabelaConsultada], quando: date) -> TabelaConsultada | None:
    """Escolhe a versão vigente na data. Duas vigentes ao mesmo tempo é erro de dado.

    Levanta em vez de escolher: sobreposição de vigência é defeito de cadastro, e
    escolher uma silenciosamente produziria cálculo com a tabela errada — exatamente
    o que a auditoria deve impedir.
    """
    candidatas = [
        t
        for t in tabelas
        if (t.vigencia_inicio is None or t.vigencia_inicio <= quando)
        and (t.vigencia_fim is None or quando <= t.vigencia_fim)
    ]
    if len(candidatas) > 1:
        nomes = ", ".join(f"{t.nome}@{t.versao}" for t in candidatas)
        raise ValueError(
            f"mais de uma versão vigente em {quando.isoformat()}: {nomes}. "
            "Corrija a vigência antes de calcular."
        )
    return candidatas[0] if candidatas else None
