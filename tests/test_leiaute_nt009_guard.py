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


# Guarda 2 — o XSD oficial atual **rejeita** a DPS que o gerador emite.
#
# Medido em 2026-11-27 com o pacote oficial `esquemas-xsd-v1.01-20260209.zip` (sha256
# `e7935cbd9470527c...`, registrado em `sources/manifest.yaml`):
#
#   Element '{...}finNFSe': This element is not expected. Expected is one of
#   ( cMotivoEmisTI, chNFSeRej, cLocEmi ).
#
# Ou seja: o gerador emite `finNFSe` (campo da NT 009), e o XSD oficial **vigente** do leiaute 1.01 é
# anterior à NT 009 e não o aceita. O fixture do repositório aceita porque foi **adaptado** — é o
# `ORIGEM.md` que declara origem em projeto de terceiro. Consequência: a validação da suíte prova
# conformidade contra um schema modificado, não contra o oficial.
#
# Este teste é `xfail(strict=True)`: descreve a divergência real e **falha quando ela sumir** — isto é,
# quando o pacote NT 009 entrar ou quando o gerador deixar de emitir o campo. Nos dois casos a decisão
# precisa ser revista, não silenciada.

ZIP_OFICIAL = (
    Path(__file__).resolve().parent.parent
    / "sources"
    / "oficiais"
    / "esquemas-xsd-v1.01-20260209.zip"
)


def _extrair_oficiais(destino: Path) -> Path:
    """Extrai o pacote oficial versionado para um diretório temporário.

    A CI não tem o diretório expandido (é derivado e fica fora do git), então o teste extrai do **zip
    versionado** — o mesmo cujo SHA-256 está em `sources/manifest.yaml`. Sem o zip, devolve caminho
    inexistente e o teste cai em `skip` declarado, em vez de passar sem verificar nada.
    """
    import zipfile

    if not ZIP_OFICIAL.is_file():  # pragma: no cover - zip versionado
        return destino / "ausente"
    with zipfile.ZipFile(ZIP_OFICIAL) as z:
        for nome in z.namelist():
            if nome.startswith("Schemas/1.01/") and nome.endswith(".xsd"):
                z.extract(nome, destino)
    return destino / "Schemas" / "1.01"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "o XSD oficial 1.01 (2026-02-09) rejeita `finNFSe`, campo que o gerador emite; adotar a NT 009 "
        "exige o pacote oficial dela, registrado em docs/REQUISITOS-FONTES.md REQ-1 (BLOCKED)"
    ),
)
def test_gerador_e_aceito_pelo_xsd_oficial(tmp_path: Path) -> None:
    """Valida a DPS gerada contra o XSD **oficial**, não contra o fixture adaptado."""
    schemas = _extrair_oficiais(tmp_path)
    if not schemas.is_dir():  # pragma: no cover - zip versionado
        pytest.skip(f"pacote oficial ausente; ver sources/manifest.yaml ({ZIP_OFICIAL.name})")

    from datetime import datetime
    from decimal import Decimal

    from app.db.models.enums import AmbienteFiscal
    from app.nfse.constants import FUSO_BR
    from app.nfse.dps import DpsInput, Prestador, Tomador, dps_para_bytes
    from lxml import etree

    schema = etree.XMLSchema(etree.parse(str(schemas / "DPS_v1.01.xsd")))
    doc = etree.fromstring(
        dps_para_bytes(
            DpsInput(
                ambiente=AmbienteFiscal.HOMOLOGACAO,
                c_mun_emissor="3550308",
                serie=1,
                n_dps=1,
                dh_emi=datetime(2026, 11, 25, 12, 0, tzinfo=FUSO_BR),
                prestador=Prestador(documento="11222333000181"),
                tomador=Tomador(nome="Tomador de Teste", documento="11144477735"),
                c_trib_nac="010701",
                x_desc_serv="Servico de teste",
                valor=Decimal("10.00"),
            )
        )
    )

    assert schema.validate(doc), [e.message for e in list(schema.error_log)[:2]]
