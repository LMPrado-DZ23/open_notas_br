"""Resposta REAL da SEFAZ-GO (status, homologação) — prova de fogo do parser.

`tests/fixtures/evidencias/sefaz_go_status_homolog_2026-11-26.xml` não foi escrito à mão: é a
resposta literal de `NFeStatusServico4` em `homolog.sefaz.go.gov.br`, obtida em 2026-11-26 com
o certificado A1 da empresa (mTLS, SOAP 1.2).

Vale como teste porque os demais fixtures de retorno foram construídos a partir do leiaute; este
vem do sistema que o consome em produção. Se o parser só funcionar no fixture feito em casa, ele
não está pronto.
"""

from __future__ import annotations

import pathlib

from app.nfe.retorno import ler
from app.nfe.soap import desenvelopar
from lxml import etree

EVIDENCIA = (
    pathlib.Path(__file__).parent
    / "fixtures"
    / "evidencias"
    / "sefaz_go_status_homolog_2026-11-26.xml"
)


class TestRespostaRealDASefaz:
    def test_arquivo_de_evidencia_existe(self) -> None:
        assert EVIDENCIA.is_file(), "a evidência da chamada real precisa estar versionada"
        assert EVIDENCIA.stat().st_size > 0

    def test_pipeline_real_envelope_e_retorno(self) -> None:
        # A resposta gravada é o envelope SOAP inteiro, como a SEFAZ devolve. O pipeline real é
        # desenvelopar e só então interpretar — este teste exercita os dois contra dado real.
        fiscal = etree.tostring(desenvelopar(EVIDENCIA.read_bytes()))
        retorno = ler(fiscal)
        # 107 = "Serviço em operação". É o código que a SEFAZ devolveu de fato.
        assert retorno.cstat == "107"
        assert retorno.xmotivo == "Serviço em operação"

    def test_metadata_da_resposta_real(self) -> None:
        bruto = EVIDENCIA.read_text(encoding="utf-8")
        # Prova que é de homologação de GO, e não um retorno inventado.
        assert "<tpAmb>2</tpAmb>" in bruto
        assert "<cUF>52</cUF>" in bruto
        assert "GO4.0" in bruto
