"""Guarda contra divergência entre leiaute declarado e XSD disponível (§80).

O código declara que homologação opera no leiaute **NT 009** (`constants.LEIAUTE_NT009`), mas o pacote
de schemas do repositório é `nfse-1.01` e **não contém** os elementos da NT 009 (`finNFSe`,
`vAjusteBC`, `indDest`). Enquanto o XSD oficial não estiver versionado, validar "NT 009" contra o
schema que existe dá falsa segurança: o schema aceitaria o documento antigo e recusaria o novo.

Este teste é `xfail(strict=True)` de propósito:

- **passa como xfail enquanto o gap existir** (o teste falha ao encontrar o XSD, que é o esperado);
- **falha se alguém adicionar o XSD** — e aí a marcação precisa sair, forçando a validação real a
  entrar no lugar do "esperado falhar".

É o oposto de relaxar expectativa: a suíte fica verde **com o gap documentado**, e o dia da correção
quebra o teste de propósito.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from app.nfse import constants

DIR_SCHEMAS = Path(__file__).parent / "fixtures" / "schemas" / "nfse-1.01"

#: Elementos que só existem a partir da NT 009. Se o XSD os tiver, o pacote está atualizado.
MARCADORES_NT009 = ("finNFse", "vAjusteBC")


def _xsds() -> list[Path]:
    return sorted(DIR_SCHEMAS.glob("*.xsd"))


@pytest.mark.xfail(
    strict=True,
    reason=(
        "XSD oficial da NT 009 (2026-11-24) não está no repositório: o pacote é nfse-1.01 e não "
        "declara finNFSe/vAjusteBC. Bloqueio externo documentado em docs/auditoria_inicial.md §80."
    ),
)
def test_xsd_acompanha_o_leiaute_declarado() -> None:
    xsds = _xsds()
    assert xsds, "nenhum XSD encontrado — o caminho do fixture mudou?"

    conteudo = "\n".join(x.read_text(encoding="utf-8", errors="ignore") for x in xsds)
    leiaute = constants.leiaute(constants.AmbienteFiscal.HOMOLOGACAO)

    if leiaute != constants.LEIAUTE_NT009:
        pytest.skip("homologação não está na NT 009: nada a comparar")
    faltando = [
        m for m in MARCADORES_NT009 if not re.search(rf"<xs:element[^>]*name=\"{m}\"", conteudo)
    ]
    assert not faltando, (
        f"leiaute declarado é {leiaute}, mas o XSD do repositório não declara {faltando}. "
        "Ou o pacote oficial da NT 009 entra com hash/registro, ou o leiaute declarado volta atrás."
    )
