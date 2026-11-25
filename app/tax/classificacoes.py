"""Catálogo de classificação tributária do IBS/CBS (cClassTrib).

Dados extraídos do SQL da calculadora oficial da Receita por
`scripts/extrair_classificacoes.py`. O arquivo vai no pacote porque é dado de
referência estável — não é resultado de cálculo nem muda em runtime.

**Ponto que a extração revelou:** o catálogo é **versionado por vigência** e
**reusa códigos entre versões**. O código `000001` existe com a descrição
"Situações tributadas integralmente pelo IBS e CBS" (vigência 2026) e com
"Primeiro fornecimento a qualquer título de bem" (vigência 2027). Por isso:

- nada aqui deduplica por código;
- toda consulta é por `(código, ano)`, e não só por código;
- sem ano, a busca devolve a versão de vigência mais recente e **avisa**.

Validar uma nota de 2026 contra a classificação de 2027 seria erro silencioso.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

CAMINHO_DADOS = Path(__file__).parent / "data" / "classificacoes_ibscbs.json"


@dataclass(frozen=True, slots=True)
class Classificacao:
    """Uma classificação tributária em uma vigência."""

    id: str
    codigo: str
    descricao: str
    tipo_aliquota: str = ""
    nomenclatura: str = ""
    situacao_tributaria_id: str = ""
    inicio_vigencia: str = ""
    fim_vigencia: str = ""
    anexo: str = ""

    def vigente_em(self, quando: date) -> bool:
        """True se a data cai dentro do intervalo de vigência declarado.

        Atenção: isto **não** considera substituição. No catálogo oficial uma
        versão nova do mesmo código entra em vigor sem que a anterior receba data
        fim, e a anterior deixa de valer por substituição. Quem resolve isso é
        `vigentes_em()`, que escolhe a versão mais recente por código.
        """
        inicio = self.inicio_vigencia
        fim = self.fim_vigencia
        momento = quando.isoformat()
        return not (inicio and momento < inicio) and not (fim and momento > fim)

    def to_dict(self) -> dict[str, Any]:
        return {
            "codigo": self.codigo,
            "descricao": self.descricao,
            "tipo_aliquota": self.tipo_aliquota,
            "nomenclatura": self.nomenclatura,
            "inicio_vigencia": self.inicio_vigencia,
            "fim_vigencia": self.fim_vigencia,
            "anexo": self.anexo,
        }


@lru_cache(maxsize=1)
def _carregar() -> tuple[Classificacao, ...]:
    if not CAMINHO_DADOS.exists():  # pragma: no cover - pacote mal montado
        return ()
    bruto = json.loads(CAMINHO_DADOS.read_text(encoding="utf-8"))
    return tuple(Classificacao(**item) for item in bruto["classificacoes"])


def metadados() -> dict[str, Any]:
    """Procedência do catálogo, para expor na API e auditar."""
    if not CAMINHO_DADOS.exists():  # pragma: no cover
        return {"fonte": "ausente", "total": 0}
    bruto = json.loads(CAMINHO_DADOS.read_text(encoding="utf-8"))
    return {
        "fonte": bruto.get("fonte"),
        "total": bruto.get("total"),
        "codigos_distintos": bruto.get("codigos_distintos"),
        "aviso": bruto.get("aviso"),
    }


def todas() -> tuple[Classificacao, ...]:
    """Todas as classificações, de todas as vigências."""
    return _carregar()


def vigentes_em(quando: date) -> tuple[Classificacao, ...]:
    """Classificações válidas na data, uma por código.

    Por código, vale a versão mais recente cujo início não seja futuro. Uma
    versão posterior substitui a anterior mesmo sem data-fim na anterior — é como
    o catálogo oficial funciona e como a SEFIN espera.
    """
    por_codigo: dict[str, Classificacao] = {}
    for classificacao in _carregar():
        if classificacao.inicio_vigencia and quando.isoformat() < classificacao.inicio_vigencia:
            continue
        if classificacao.fim_vigencia and quando.isoformat() > classificacao.fim_vigencia:
            continue
        atual = por_codigo.get(classificacao.codigo)
        if atual is None or classificacao.inicio_vigencia > atual.inicio_vigencia:
            por_codigo[classificacao.codigo] = classificacao
    return tuple(sorted(por_codigo.values(), key=lambda c: c.codigo))


def buscar(codigo: str, *, quando: date | None = None) -> Classificacao | None:
    """Busca por código, preferindo a versão vigente na data.

    Sem data, devolve a versão de vigência mais recente — comportamento
    documentado, não acidente. Quem valida nota deve informar a competência.
    """
    candidatas = [c for c in _carregar() if c.codigo == codigo]
    if not candidatas:
        return None
    if quando is not None:
        aplicaveis = [
            c
            for c in candidatas
            if (not c.inicio_vigencia or c.inicio_vigencia <= quando.isoformat())
            and (not c.fim_vigencia or c.fim_vigencia >= quando.isoformat())
        ]
        if aplicaveis:
            return max(aplicaveis, key=lambda c: c.inicio_vigencia)
        return None
    return max(candidatas, key=lambda c: c.inicio_vigencia)


def pesquisar(texto: str, *, quando: date | None = None, limite: int = 50) -> list[Classificacao]:
    """Busca por trecho da descrição ou pelo código."""
    alvo = texto.strip().lower()
    fonte = vigentes_em(quando) if quando is not None else _carregar()
    if not alvo:
        return list(fonte)[:limite]

    encontradas = [c for c in fonte if alvo in c.descricao.lower() or alvo in c.codigo]
    return encontradas[:limite]
