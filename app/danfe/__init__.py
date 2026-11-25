"""Representações impressas de documentos fiscais.

Registra as representações disponíveis no import, para que a interface
`RepresentacaoImpressa` tenha conteúdo sem passo manual de bootstrap.
"""

from app.danfe.base import (
    ErroRepresentacao,
    RepresentacaoImpressa,
    RepresentacaoNaoImplementada,
    TipoRepresentacao,
    disponiveis,
    gerar,
    obter,
    registrar,
)
from app.danfe.nfe import DanfeSimplificado, Danfse, registrar_todas

registrar_todas()

__all__ = [
    "DanfeSimplificado",
    "Danfse",
    "ErroRepresentacao",
    "RepresentacaoImpressa",
    "RepresentacaoNaoImplementada",
    "TipoRepresentacao",
    "disponiveis",
    "gerar",
    "obter",
    "registrar",
]
