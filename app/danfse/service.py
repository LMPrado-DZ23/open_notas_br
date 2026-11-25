"""Serviço de geração do DANFSe a partir do documento fiscal persistido."""

from __future__ import annotations

from app.danfse.parser import parse_danfse
from app.danfse.render import gerar_danfse
from app.db.models.invoice import FiscalDocument


class ErroDanfse(Exception):
    """Não foi possível gerar o DANFSe."""


def gerar_pdf_do_documento(documento: FiscalDocument) -> bytes:
    """Gera o PDF a partir do XML autorizado do documento.

    Só o XML **autorizado** serve: o DANFSe representa documento autorizado, não
    rascunho. Se o documento ainda não foi autorizado, o erro diz isso em vez de
    gerar PDF de nota inexistente.
    """
    xml = documento.xml_autorizado
    if not xml:
        raise ErroDanfse(
            "documento sem XML autorizado: o DANFSe representa a NFS-e autorizada, "
            "não a DPS enviada"
        )
    dados = parse_danfse(xml)
    return gerar_danfse(dados)
