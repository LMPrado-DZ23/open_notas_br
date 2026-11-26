"""Validação de XML de CT-e contra o schema oficial 4.00.

O gerador de CT-e ainda não existe; esta camada existe para que ele nasça **validado**. Sem
isso, o gerador produz XML que parece correto e é recusado na primeira transmissão, sem
indicar o campo errado.

Schema: `tests/fixtures/schemas/cte-4.00/cte_v4.00.xsd`, obtido do Portal do Conhecimento de
Transporte Eletrônico (origem, data e hash em `ORIGEM.md` e `data/xsd_manifest.json`).
"""

from __future__ import annotations

import enum
from functools import lru_cache
from pathlib import Path

from lxml import etree

RAIZ = Path(__file__).resolve().parents[2]
DIR_SCHEMAS = RAIZ / "tests" / "fixtures" / "schemas" / "cte-4.00"
#: Schema raiz do CT-e (modelo 57). Os demais são incluídos por `xs:import`.
SCHEMA_PRINCIPAL = DIR_SCHEMAS / "cte_v4.00.xsd"


class PapelTomador(enum.StrEnum):
    """Código `toma` do leiaute: quem é o tomador do serviço.

    Existe para que o gerador **não escolha** o grupo de tomador por conta própria. Escolher
    `toma3` por omissão produz XML válido contra o schema e fiscalmente incorreto — o tomador
    aparece como destinatário quando não é.

    Os valores são os do leiaute, não invenção nossa.
    """

    REMETENTE = "0"
    EXPEDIDOR = "1"
    RECEBEDOR = "2"
    DESTINATARIO = "3"
    OUTROS = "4"

    @property
    def grupo(self) -> str:
        """Qual bloco do `ide` este papel exige.

        `toma3` serve quando o tomador é uma das partes já identificadas no documento.
        `OUTROS` (4) exige `toma4`, com documento e endereço próprios.
        """
        return "toma3" if self is not PapelTomador.OUTROS else "toma4"

    @property
    def exige_dados_proprios(self) -> bool:
        return self.grupo == "toma4"


class ErroCTe(Exception):
    """XML inválido para o leiaute do CT-e."""


@lru_cache(maxsize=1)
def _validador() -> etree.XMLSchema:
    """Carrega o schema uma vez por processo.

    `lru_cache` porque compilar XSD é caro e o resultado é imutável. Se o arquivo mudar, o
    processo precisa reiniciar — o que é o comportamento certo: schema trocado em runtime é
    evento de deploy, não de requisição.
    """
    if not SCHEMA_PRINCIPAL.is_file():
        raise ErroCTe(
            f"schema do CT-e ausente em {SCHEMA_PRINCIPAL}; "
            "veja tests/fixtures/schemas/cte-4.00/ORIGEM.md"
        )
    try:
        return etree.XMLSchema(etree.parse(str(SCHEMA_PRINCIPAL)))
    except etree.XMLSchemaParseError as exc:
        raise ErroCTe(f"schema do CT-e inválido: {exc}") from exc


def validar(xml: bytes) -> None:
    """Valida contra o schema. Não retorna nada; levanta `ErroCTe` com a linha do erro."""
    try:
        raiz = etree.fromstring(xml)
    except etree.XMLSyntaxError as exc:
        raise ErroCTe(f"XML malformado: {exc}") from exc

    validador = _validador()
    if validador.validate(raiz):
        return

    # A primeira mensagem basta: a segunda em diante costuma ser consequência dela.
    erro = validador.error_log[0]
    raise ErroCTe(f"leiaute do CT-e: {erro.message} (linha {erro.line})")


def validar_ou_levantar(xml: bytes, *, resumo: str = "CT-e") -> bytes:
    """Conveniência para o futuro gerador: valida e devolve o mesmo XML."""
    validar(xml)
    return xml
