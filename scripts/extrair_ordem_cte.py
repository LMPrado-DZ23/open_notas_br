"""Extrai a ordem exigida dos elementos de um grupo do leiaute a partir do XSD.

Motivo: escrever gerador de XML "de memória" produz ordem errada, e o schema recusa por
sequência antes mesmo de olhar o conteúdo. A ordem correta está no próprio XSD; extrair é
determinístico e não depende de adivinhação.

Uso:
    python -m scripts.extrair_ordem_cte            # grupo `ide`
    python -m scripts.extrair_ordem_cte emit
"""

from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree

XS = "{http://www.w3.org/2001/XMLSchema}"
DIR = Path("tests/fixtures/schemas/cte-4.00")


def rotulo(elemento) -> str:
    if elemento.tag == XS + "choice":
        nomes = [c.get("name") or c.get("ref") or "?" for c in elemento.iter(XS + "element")]
        return "escolha(" + "/".join(nomes) + ")"
    nome = elemento.get("name") or elemento.get("ref") or "?"
    return nome + ("?" if elemento.get("minOccurs") == "0" else "")


def ordem(grupo: str) -> list[str]:
    """Sequência declarada de `grupo`, procurando em todos os XSD do pacote."""
    for arq in sorted(DIR.glob("*.xsd")):
        try:
            doc = etree.parse(str(arq))
        except etree.XMLSyntaxError:
            continue
        for el in doc.iter(XS + "element"):
            if el.get("name") != grupo:
                continue
            seq = el.find(f"{XS}complexType/{XS}sequence")
            if seq is None:
                continue
            return [rotulo(e) for e in seq]
    return []


def main(argv: list[str] | None = None) -> int:
    grupo = (argv or sys.argv[1:] or ["ide"])[0]
    itens = ordem(grupo)
    if not itens:
        print(f"grupo '{grupo}' não encontrado em {DIR}")
        return 1
    print(f"{grupo}: {len(itens)} elementos (ordem obrigatória)")
    for indice, item in enumerate(itens, start=1):
        print(f"{indice:3}. {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
