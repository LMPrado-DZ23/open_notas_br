"""Contrato de erro unificado — RFC 7807 (`application/problem+json`).

Seção 1.4 do v10.0. Implementado **antes** das fases porque toda rota nova precisa
responder erro no mesmo formato, e retrofit é mais caro que adoção.

Regras que este módulo respeita:

- **Não muda status code existente.** Um 422 continua 422; muda só o corpo. Isso é o
  que torna a mudança retrocompatível com o `/v1` congelado (R2/P5) — clientes que
  liam `{"detail": ...}` continuam funcionando porque `detail` é preservado em
  `detail` do problem.
- **Erro de SEFAZ nunca vira 200** (P4): a rejeição carrega `origem=SEFAZ`,
  `codigo_sefaz` e `retryable`, e o status vem do mapeamento, nunca de um default.
- **Nenhum dado sensível** no corpo: `tenant_id` é o UUID do tenant (não é segredo),
  e não há payload fiscal nem credencial.

`retryable` responde à pergunta que o cliente realmente faz: "tento de novo?". Erro
de schema é definitivo; timeout e 5xx são transitórios.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

BASE_URI = "https://opennotas.dev/errors"


class OrigemErro(StrEnum):
    """De onde veio a falha. Muda a ação esperada de quem consome."""

    SEFAZ = "SEFAZ"
    MUNICIPIO = "MUNICIPIO"
    VALIDACAO = "VALIDACAO"
    INTERNO = "INTERNO"


@dataclass(frozen=True, slots=True)
class Problema:
    """Um erro no formato RFC 7807."""

    titulo: str
    status: int
    detalhe: str
    tipo: str = "about:blank"
    origem: OrigemErro = OrigemErro.INTERNO
    codigo_sefaz: str | None = None
    retryable: bool = False
    instancia: str | None = None
    tenant_id: str | None = None
    request_id: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def para_dict(self) -> dict[str, Any]:
        corpo: dict[str, Any] = {
            "type": self.tipo,
            "title": self.titulo,
            "status": self.status,
            "detail": self.detalhe,
            "origem": str(self.origem),
            "retryable": self.retryable,
        }
        if self.instancia:
            corpo["instance"] = self.instancia
        if self.codigo_sefaz:
            corpo["codigo_sefaz"] = self.codigo_sefaz
        if self.tenant_id:
            corpo["tenant_id"] = self.tenant_id
        if self.request_id:
            corpo["request_id"] = self.request_id
        corpo.update(self.extras)
        return corpo


def sefaz(
    codigo: str | None,
    descricao: str,
    *,
    status: int = 422,
    retryable: bool = False,
    origem: OrigemErro = OrigemErro.SEFAZ,
) -> Problema:
    """Erro devolvido pela SEFAZ/prefeitura, já normalizado."""
    sufixo = f"-cstat-{codigo}" if codigo else ""
    return Problema(
        tipo=f"{BASE_URI}/sefaz{sufixo}",
        titulo=f"Rejeição {str(origem).title()}" + (f" {codigo}" if codigo else ""),
        status=status,
        detalhe=descricao[:2000],
        origem=origem,
        codigo_sefaz=codigo,
        retryable=retryable,
    )


def validacao(detalhe: str, *, status: int = 422) -> Problema:
    return Problema(
        tipo=f"{BASE_URI}/validacao",
        titulo="Requisição inválida",
        status=status,
        detalhe=detalhe[:2000],
        origem=OrigemErro.VALIDACAO,
    )


def nao_encontrado(detalhe: str) -> Problema:
    return Problema(
        tipo=f"{BASE_URI}/nao-encontrado",
        titulo="Recurso não encontrado",
        status=404,
        detalhe=detalhe[:2000],
        origem=OrigemErro.VALIDACAO,
    )


def conflito(detalhe: str) -> Problema:
    return Problema(
        tipo=f"{BASE_URI}/conflito",
        titulo="Conflito de estado",
        status=409,
        detalhe=detalhe[:2000],
        origem=OrigemErro.VALIDACAO,
    )


def interno(detalhe: str) -> Problema:
    return Problema(
        tipo=f"{BASE_URI}/interno",
        titulo="Erro interno",
        status=500,
        detalhe=detalhe[:2000],
        origem=OrigemErro.INTERNO,
        retryable=True,
    )


#: Status HTTP que valem nova tentativa. 5xx e 503 (circuito aberto) entram aqui;
#: 4xx de validação não, porque repetir a mesma requisição dá o mesmo erro.
TRANSITORIOS = frozenset({500, 502, 503, 504})


def de_http_exception(status: int, detalhe: Any) -> Problema:
    """Converte uma `HTTPException` do FastAPI preservando status e `detail`.

    `detail` continua existindo no corpo para não quebrar cliente que já lê esse
    campo — é o que torna a migração aditiva de verdade.
    """
    # `detail` pode ser dict (ex.: erro da SEFIN com tipo/mensagens). `str(dict)` vira repr e o
    # cliente recebe um texto impossível de parsear; aqui o dict vira campos extras do problema.
    extras: dict[str, Any] = {}
    if isinstance(detalhe, str):
        texto = detalhe
    elif isinstance(detalhe, dict):
        extras = dict(detalhe)
        resumo = detalhe.get("mensagem") or detalhe.get("detail") or detalhe.get("motivo")
        # Nunca `str(dict)`: o cliente receberia repr. Sem campo de resumo, monta `chave=valor`,
        # que é legível e não finge ser texto livre.
        texto = (
            str(resumo)
            if resumo
            else "erro estruturado: "
            + ", ".join(f"{chave}={valor}" for chave, valor in detalhe.items())
        )
    else:
        texto = str(detalhe)
    base = {
        404: nao_encontrado,
        409: conflito,
        422: validacao,
    }.get(status)
    problema = (
        base(texto)
        if base
        else Problema(
            tipo=f"{BASE_URI}/http-{status}",
            titulo=f"Erro HTTP {status}",
            status=status,
            detalhe=texto[:2000],
            retryable=status in TRANSITORIOS,
        )
    )
    problema.extras.update(extras)
    return Problema(
        tipo=problema.tipo,
        titulo=problema.titulo,
        status=problema.status,
        detalhe=problema.detalhe,
        origem=problema.origem,
        retryable=problema.retryable,
        extras={**problema.extras, **extras, "detail": texto[:2000]},
    )
