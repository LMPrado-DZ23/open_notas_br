"""Validação de XML de MDF-e contra o schema oficial 3.00.

Mesma função do validador de CT-e: existir **antes** do gerador, para que ele nasça validado.
Sem isso, o gerador produz XML bem formado e inválido, e o erro só aparece no autorizador.

Schema: `tests/fixtures/schemas/mdfe-3.00/mdfe_v3.00.xsd`, procedência em `ORIGEM.md` e hash
em `data/xsd_manifest.json`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from lxml import etree

DIR_SCHEMAS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "schemas" / "mdfe-3.00"
SCHEMA_PRINCIPAL = DIR_SCHEMAS / "mdfe_v3.00.xsd"


class ErroMDFe(Exception):
    """XML inválido para o leiaute do MDF-e."""


@lru_cache(maxsize=1)
def _validador() -> etree.XMLSchema:
    if not SCHEMA_PRINCIPAL.is_file():
        raise ErroMDFe(
            f"schema do MDF-e ausente em {SCHEMA_PRINCIPAL}; "
            "veja tests/fixtures/schemas/mdfe-3.00/ORIGEM.md"
        )
    try:
        return etree.XMLSchema(etree.parse(str(SCHEMA_PRINCIPAL)))
    except etree.XMLSchemaParseError as exc:
        raise ErroMDFe(f"schema do MDF-e inválido: {exc}") from exc


def validar(xml: bytes) -> None:
    """Valida contra o schema. Levanta `ErroMDFe` com o campo e a linha do primeiro erro."""
    try:
        raiz = etree.fromstring(xml)
    except etree.XMLSyntaxError as exc:
        raise ErroMDFe(f"XML malformado: {exc}") from exc

    validador = _validador()
    if validador.validate(raiz):
        return

    erro = validador.error_log[0]
    raise ErroMDFe(f"leiaute do MDF-e: {erro.message} (linha {erro.line})")
