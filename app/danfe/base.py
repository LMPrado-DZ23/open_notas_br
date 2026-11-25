"""Interface unificada de representação impressa.

Um documento fiscal não tem "um PDF": tem representações distintas. Modelar como
um único gerador produz layout errado em produção, porque DANFE de NF-e, DANFSe,
cupom de NFC-e e etiqueta de envio têm campos obrigatórios diferentes.

Aqui a representação é escolhida pelo **tipo de documento** e pelo **tipo de
representação** pedido. Quem pede um tipo não implementado recebe erro explícito
de domínio — não um PDF vazio nem um placeholder silencioso.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class ErroRepresentacao(Exception):
    """Base dos erros de representação impressa."""


class RepresentacaoNaoImplementada(ErroRepresentacao):
    """O tipo de representação ainda não existe para este documento.

    Erro explícito, com o nome do que falta. Nunca devolve documento incompleto:
    representação impressa incompleta é pior que ausência, porque parece válida.
    """


@dataclass(frozen=True, slots=True)
class TipoRepresentacao:
    """Identifica uma representação impressa."""

    documento: str  # nfe | nfce | nfse | cte | mdfe
    formato: str  # danfe | danfe_simplificado | danfse | cupom | dacte | damdfe


@runtime_checkable
class RepresentacaoImpressa(Protocol):
    """Contrato de um gerador de representação."""

    tipo: TipoRepresentacao

    def gerar(self, xml: bytes) -> bytes:
        """Devolve o PDF da representação a partir do XML autorizado."""
        ...


_REGISTRO: dict[TipoRepresentacao, RepresentacaoImpressa] = {}


def registrar(representacao: RepresentacaoImpressa) -> RepresentacaoImpressa:
    """Registra uma representação no catálogo."""
    _REGISTRO[representacao.tipo] = representacao
    return representacao


def disponiveis() -> list[TipoRepresentacao]:
    """Representações registradas, para diagnóstico e OpenAPI."""
    return sorted(_REGISTRO, key=lambda t: (t.documento, t.formato))


def obter(documento: str, formato: str) -> RepresentacaoImpressa:
    """Representação registrada, ou erro explícito do que falta."""
    chave = TipoRepresentacao(documento=documento, formato=formato)
    achada = _REGISTRO.get(chave)
    if achada is None:
        existentes = ", ".join(f"{t.documento}/{t.formato}" for t in disponiveis()) or "nenhuma"
        raise RepresentacaoNaoImplementada(
            f"não existe representação {documento}/{formato}. Disponíveis: {existentes}. "
            "DANFE A4 de NF-e e DACTE/DAMDFE entram nas fases 7 e 8."
        )
    return achada


def gerar(documento: str, xml: bytes, *, formato: str) -> bytes:
    """Atalho: gera a representação pedida."""
    return obter(documento, formato).gerar(xml)
