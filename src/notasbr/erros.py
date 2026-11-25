"""Exceções do notasbr.

Todas herdam de `NotaFiscalError`, então um `except NotaFiscalError` cobre o
domínio inteiro sem capturar erro de programação por acidente.
"""

from __future__ import annotations


class NotaFiscalError(Exception):
    """Base de todos os erros de domínio do notasbr."""


class XmlInvalido(NotaFiscalError):
    """O conteúdo não é XML bem formado, ou foi recusado por segurança."""


class DocumentoNaoSuportado(NotaFiscalError):
    """O XML é válido, mas não é um documento fiscal que esta versão audita."""


class ChaveInvalida(NotaFiscalError):
    """A chave de acesso não tem 44 dígitos, ou o dígito verificador não fecha."""


class ArquivoGrandeDemais(NotaFiscalError):
    """O arquivo excede o limite de leitura configurado."""
