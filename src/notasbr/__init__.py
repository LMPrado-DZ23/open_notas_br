"""notasbr — auditoria offline de documentos fiscais brasileiros.

O pacote não faz transmissão para a SEFAZ e não emite documento fiscal. Ele lê
XML de NF-e, NFC-e e CT-e e responde, regra por regra, o que está inconsistente.

Uso mínimo::

    from notasbr import auditar_arquivo

    relatorio = auditar_arquivo("nota.xml")
    print(relatorio.resumo.erros)
"""

from .auditor import auditar_arquivo, auditar_bytes
from .chave import ChaveAcesso, calcular_dv, chave_valida
from .erros import (
    ChaveInvalida,
    DocumentoNaoSuportado,
    NotaFiscalError,
    XmlInvalido,
)
from .modelos import Achado, Pulada, Relatorio, Resumo, Severidade
from .versao import SCHEMA_RELATORIO, VERSAO

__version__ = VERSAO

__all__ = [
    "SCHEMA_RELATORIO",
    "VERSAO",
    "Achado",
    "ChaveAcesso",
    "ChaveInvalida",
    "DocumentoNaoSuportado",
    "NotaFiscalError",
    "Pulada",
    "Relatorio",
    "Resumo",
    "Severidade",
    "XmlInvalido",
    "__version__",
    "auditar_arquivo",
    "auditar_bytes",
    "calcular_dv",
    "chave_valida",
]
