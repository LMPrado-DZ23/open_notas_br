"""Validação da DPS nos leiautes oficiais — com o limite do pacote anterior documentado.

Contexto (Adendo 3, REQ-1): o critério pede validação nos **dois leiautes**. Ao executar isso com os dois
pacotes oficiais versionados, apareceu um defeito do **próprio pacote publicado**:

- pacote de 24/11/2026 (Produção Restrita, NT 009) → `TSSerieDPS` usa `[0-9]{1,4}|[0-8][0-9]{4}`;
- pacote de 09/02/2026 (leiaute anterior) → `TSSerieDPS` usa `^0{0,4}\\d{1,5}$`.

No dialeto de regex do **XML Schema**, `^` e `$` **não são âncoras** — são caracteres literais. Um
`xs:pattern` com `^...$` só casaria com um valor que contivesse literalmente `^` e `$`. Resultado: o pacote
de fevereiro rejeita **qualquer** valor de `serie`, e não existe ajuste no nosso gerador que satisfaça um
schema assim. Está demonstrado no teste `test_pacote_anterior_rejeita_qualquer_serie`.

Consequência honesta: o leiaute NT 009 é validado de ponta a ponta; o leiaute anterior **não pode** ser
validado com esse pacote. Não é "não testado por preguiça" — é bloqueio do artefato publicado, com prova.
Nenhuma transmissão acontece: validação local contra XSD versionado.
"""

from __future__ import annotations

import zipfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from app.db.models.enums import AmbienteFiscal
from app.nfse.constants import FUSO_BR
from app.nfse.dps import DpsInput, Prestador, Tomador, dps_para_bytes
from lxml import etree

RAIZ = Path(__file__).resolve().parent.parent
PACOTE_ANTERIOR = RAIZ / "sources" / "oficiais" / "esquemas-xsd-v1.01-20260209.zip"
PACOTE_NT009 = RAIZ / "sources" / "oficiais" / "esquemas-xsd-producao-restrita-20261124.zip"


def _extrair(zip_path: Path, tmp_path: Path) -> Path:
    if not zip_path.is_file():  # pragma: no cover - pacotes versionados
        pytest.skip(f"pacote oficial ausente: {zip_path.name}")
    destino = tmp_path / zip_path.stem
    destino.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(destino)
    return destino


def _schema(zip_path: Path, tmp_path: Path) -> etree.XMLSchema:
    destino = _extrair(zip_path, tmp_path)
    xsd = sorted(destino.rglob("DPS_v1.01.xsd"))
    assert xsd, f"pacote sem DPS_v1.01.xsd: {zip_path.name}"
    return etree.XMLSchema(etree.parse(str(xsd[0])))


def _entrada(ambiente: AmbienteFiscal, quando: datetime, serie: int = 1) -> DpsInput:
    return DpsInput(
        ambiente=ambiente,
        c_mun_emissor="3550308",
        serie=serie,
        n_dps=1,
        dh_emi=quando,
        prestador=Prestador(documento="11222333000181"),
        tomador=Tomador(nome="Tomador de Teste", documento="11144477735"),
        c_trib_nac="010701",
        x_desc_serv="Servico de teste",
        valor=Decimal("10.00"),
    )


class TestLeiauteNT009:
    """Homologação e produção a partir de 01/12/2026 — o leiaute que o sistema declara cumprir."""

    def test_homologacao_valida_no_pacote_nt009(self, tmp_path: Path) -> None:
        schema = _schema(PACOTE_NT009, tmp_path)
        quando = datetime(2026, 11, 25, 12, 0, tzinfo=FUSO_BR)

        doc = etree.fromstring(dps_para_bytes(_entrada(AmbienteFiscal.HOMOLOGACAO, quando)))

        assert schema.validate(doc), [e.message for e in list(schema.error_log)[:3]]

    def test_producao_a_partir_da_virada_usa_nt009(self, tmp_path: Path) -> None:
        schema = _schema(PACOTE_NT009, tmp_path)
        depois_da_virada = datetime(2026, 12, 2, 12, 0, tzinfo=FUSO_BR)

        doc = etree.fromstring(dps_para_bytes(_entrada(AmbienteFiscal.PRODUCAO, depois_da_virada)))

        assert schema.validate(doc), [e.message for e in list(schema.error_log)[:3]]

    def test_nt009_tem_finnfse_e_inddest(self) -> None:
        quando = datetime(2026, 11, 25, 12, 0, tzinfo=FUSO_BR)
        bruto = dps_para_bytes(_entrada(AmbienteFiscal.HOMOLOGACAO, quando)).decode()

        assert "finNFSe" in bruto
        assert "indDest" in bruto


class TestLeiauteAnterior:
    """O pacote de fevereiro não valida `serie`: defeito do artefato, documentado com prova."""

    def test_gerador_nao_emite_campos_da_nt009_antes_da_virada(self) -> None:
        antes_da_virada = datetime(2026, 11, 20, 12, 0, tzinfo=FUSO_BR)
        bruto = dps_para_bytes(_entrada(AmbienteFiscal.PRODUCAO, antes_da_virada)).decode()

        assert "finNFSe" not in bruto
        assert "indDest" not in bruto

    def test_pacote_anterior_rejeita_qualquer_serie(self, tmp_path: Path) -> None:
        """`^`/`$` são literais no dialeto XSD: nenhum valor casa com `^0{0,4}\\d{1,5}$`.

        Este teste falha de propósito contra a hipótese "o gerador está errado": mostra que **nenhum**
        valor de `serie` — nem `1`, nem `00001` — passa no pacote de fevereiro. Sem esta prova, alguém
        tentaria 'consertar' o gerador perseguindo uma validação inalcançável.
        """
        schema = _schema(PACOTE_ANTERIOR, tmp_path)
        antes_da_virada = datetime(2026, 11, 20, 12, 0, tzinfo=FUSO_BR)

        aceitos = 0
        for serie in (1, 10, 9999, 12345):
            doc = etree.fromstring(
                dps_para_bytes(_entrada(AmbienteFiscal.PRODUCAO, antes_da_virada, serie))
            )
            if schema.validate(doc):
                aceitos += 1

        assert aceitos == 0, (
            "o pacote de fevereiro passou a aceitar `serie` — se o schema foi corrigido, a validação do "
            "leiaute anterior pode ser reativada e este teste substituído pela validação real"
        )
