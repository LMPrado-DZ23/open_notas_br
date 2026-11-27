"""O fixture é o pacote oficial e o gerador é aceito por ele.

Histórico desta guarda, porque o motivo importa:

- §80: o fixture do repositório **não era** o XSD oficial — aceitava `finNFSe` que o pacote oficial de
  2026-02-09 rejeitava, e a suíte provava conformidade com um schema adaptado. Ficou como
  `xfail(strict=True)` para quebrar quando o gap fosse resolvido.
- §89 (27/11/2026): o pacote oficial de **24/11/2026** foi obtido
  (`esquemas-xsd-producao-restrita-20261124.zip`, sha256 `1ca83c1a…`), os fixtures foram substituídos
  pelos arquivos oficiais e o gerador passou a emitir `indDest` em `infDPS` (posição correta) em vez de
  dentro do grupo `IBSCSS`. O gap deixou de existir.

Com o gap fechado, `xfail` deixaria de fazer sentido: estes testes agora **exigem** o estado correto.
Se alguém voltar a usar schema adaptado, o primeiro teste quebra; se alguém remover `indDest`, o segundo
quebra. Nenhum dos dois depende de rede: o pacote oficial está versionado em `sources/oficiais/`.
"""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from app.nfse import constants

DIR_SCHEMAS = Path(__file__).parent / "fixtures" / "schemas" / "nfse-1.01"
ZIP_OFICIAL = (
    Path(__file__).resolve().parent.parent
    / "sources"
    / "oficiais"
    / "esquemas-xsd-producao-restrita-20261124.zip"
)

#: Elementos que só existem a partir da NT 009. Se o XSD os tiver, o pacote está atualizado.
MARCADORES_NT009 = ("finNFSe", "vAjusteBC", "indDest")


def _xsds() -> list[Path]:
    return sorted(DIR_SCHEMAS.glob("*.xsd"))


def _sha(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def test_fixtures_sao_byte_identicos_ao_pacote_oficial(tmp_path: Path) -> None:
    """Prova que o fixture **não é adaptado**: ele é o arquivo publicado, byte a byte.

    Este é o teste que faltava em §80. Comparar "campos esperados" não provava nada — o schema
    adaptado também tinha os campos. Comparar hash prova autoria.
    """
    if not ZIP_OFICIAL.is_file():  # pragma: no cover - zip versionado
        raise AssertionError(f"pacote oficial ausente: {ZIP_OFICIAL} — ver sources/manifest.yaml")

    with zipfile.ZipFile(ZIP_OFICIAL) as z:
        z.extractall(tmp_path)
        nomes = [n for n in z.namelist() if n.endswith(".xsd")]

    assert nomes, "pacote oficial sem XSD — arquivo errado?"

    divergentes: list[str] = []
    for nome in nomes:
        oficial = tmp_path / nome
        local = DIR_SCHEMAS / Path(nome).name
        if not local.is_file():
            divergentes.append(f"{Path(nome).name} (ausente no repositório)")
            continue
        if _sha(oficial) != _sha(local):
            divergentes.append(f"{Path(nome).name} (hash diferente)")

    assert not divergentes, (
        "fixture diverge do pacote oficial de 24/11/2026: "
        + ", ".join(divergentes)
        + ". Se o pacote mudou, atualize fixtures, manifesto e este teste juntos."
    )


def test_xsd_declara_os_elementos_do_leiaute_declarado() -> None:
    """O leiaute declarado em código (NT 009) precisa existir no XSD versionado."""
    conteudo = "\n".join(x.read_text(encoding="utf-8", errors="ignore") for x in _xsds())
    leiaute = constants.leiaute(constants.AmbienteFiscal.HOMOLOGACAO)

    assert leiaute == constants.LEIAUTE_NT009, "homologação deveria estar na NT 009"
    faltando = [m for m in MARCADORES_NT009 if f'name="{m}"' not in conteudo]
    assert not faltando, (
        f"leiaute declarado é {leiaute}, mas o XSD versionado não declara {faltando}"
    )


def test_gerador_emite_indest_fora_do_grupo_ibscbs() -> None:
    """`indDest` pertence a `infDPS`; dentro de `IBSCBS` o schema oficial recusa a DPS inteira."""
    from datetime import datetime
    from decimal import Decimal

    from app.db.models.enums import AmbienteFiscal
    from app.nfse.constants import FUSO_BR
    from app.nfse.dps import DpsInput, Ibscbs, Prestador, Tomador, dps_para_bytes
    from lxml import etree

    xml = dps_para_bytes(
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
            ibscbs=Ibscbs(c_ind_op="100301", c_class_trib="000001", c_nbs="123456789"),
        )
    )
    raiz = etree.fromstring(xml)
    ns = {"n": constants.NS_NFSE}

    inf = raiz.find("n:infDPS", ns)
    assert inf is not None
    ind_dest = inf.findall("n:indDest", ns)
    assert len(ind_dest) == 1, "infDPS deve ter exatamente um indDest"
    assert ind_dest[0].text in {"0", "1"}

    for grupo in inf.findall("n:IBSCBS", ns):
        assert grupo.find("n:indDest", ns) is None, "indDest não existe dentro de IBSCBS"
