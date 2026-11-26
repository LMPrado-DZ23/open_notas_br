"""Envelope do lote e consulta de status, validados no PL_010h."""

from __future__ import annotations

import pathlib
from datetime import datetime
from decimal import Decimal

import pytest
from app.nfe.assinatura import assinar_nfe
from app.nfe.base import Destinatario, Emitente, ErroDeNFe, Item, NotaFiscal
from app.nfe.gerador import gerar_nfe
from app.nfe.lote import (
    LIMITE_POR_LOTE,
    LIMITE_SINCRONO,
    interpretar_retorno_status,
    montar_consStatServ,
    montar_enviNFe,
)
from lxml import etree

from tests.test_fase2_certificado import SENHA, gerar_pfx

SCHEMAS = pathlib.Path(__file__).resolve().parent / "fixtures" / "schemas" / "nfe-4.00"


@pytest.fixture(scope="module")
def certificado():
    from app.certificates.cofre import CertificadoA1

    return CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())


def nota_assinada(certificado, numero: int = 1) -> bytes:
    nota = NotaFiscal(
        numero=numero,
        serie=1,
        emitente=Emitente(
            cnpj="11222333000181",
            nome="EMITENTE",
            ie="1234567890",
            crt="1",
            logradouro="RUA A",
            numero="1",
            bairro="CENTRO",
            municipio="AGUAS LINDAS DE GOIAS",
            codigo_municipio="5200258",
            uf="GO",
            cep="72910000",
        ),
        destinatario=Destinatario(
            documento="11144477735",
            nome="CONSUMIDOR",
            logradouro="RUA B",
            numero="2",
            bairro="CENTRO",
            municipio="GOIANIA",
            codigo_municipio="5208707",
            uf="GO",
            cep="74000000",
        ),
        itens=[
            Item(
                codigo="1",
                descricao="P",
                ncm="12345678",
                cfop="5102",
                unidade="UN",
                quantidade=Decimal("1"),
                valor_unitario=Decimal("100.00"),
                valor_total=Decimal("100.00"),
                cst="00",
                icms_situacao="102",
            )
        ],
        dh_emissao=datetime(2026, 11, 25, 12, 0),
    )
    return assinar_nfe(gerar_nfe(nota), certificado)


class TestEnvelope:
    def test_lote_valida_no_schema(self, certificado) -> None:
        schema = etree.XMLSchema(etree.parse(str(SCHEMAS / "enviNFe_v4.00.xsd")))
        lote = montar_enviNFe([nota_assinada(certificado)])
        assert schema.validate(etree.fromstring(lote)), [
            e.message for e in list(schema.error_log)[:3]
        ]

    def test_tres_notas_no_mesmo_lote(self, certificado) -> None:
        schema = etree.XMLSchema(etree.parse(str(SCHEMAS / "enviNFe_v4.00.xsd")))
        lote = montar_enviNFe([nota_assinada(certificado, n) for n in (1, 2, 3)])
        doc = etree.fromstring(lote)
        assert schema.validate(doc)
        assert len(doc.findall("{http://www.portalfiscal.inf.br/nfe}NFe")) == 3

    def test_sincrono_marca_ind_sinc_1(self, certificado) -> None:
        doc = etree.fromstring(montar_enviNFe([nota_assinada(certificado)], sincrono=True))
        assert doc.find("{*}indSinc").text == "1"

    def test_assincrono_marca_0(self, certificado) -> None:
        doc = etree.fromstring(montar_enviNFe([nota_assinada(certificado)], sincrono=False))
        assert doc.find("{*}indSinc").text == "0"

    def test_lote_vazio_recusado(self) -> None:
        with pytest.raises(ErroDeNFe, match="ao menos uma"):
            montar_enviNFe([])

    def test_acima_do_limite_do_lote(self, certificado) -> None:
        nota = nota_assinada(certificado)
        with pytest.raises(ErroDeNFe, match="no máximo"):
            montar_enviNFe([nota] * (LIMITE_POR_LOTE + 1))

    def test_sincrono_acima_do_limite(self, certificado, monkeypatch) -> None:
        # Hoje LIMITE_SINCRONO == LIMITE_POR_LOTE == 50, então a guarda do síncrono
        # é inalcançável com os valores reais. Reduzo o limite para provar que a
        # lógica existe e funciona se a SEFAZ mudar os números.
        import app.nfe.lote as modulo

        monkeypatch.setattr(modulo, "LIMITE_SINCRONO", 2)
        nota = nota_assinada(certificado)
        with pytest.raises(ErroDeNFe, match="síncrono"):
            montar_enviNFe([nota] * 3, sincrono=True)

    def test_limite_do_lote_e_o_do_sincrono_hoje(self) -> None:
        # Se a SEFAZ separar os limites, este teste avisa.
        assert LIMITE_SINCRONO == LIMITE_POR_LOTE

    def test_idlote_invalido(self, certificado) -> None:
        with pytest.raises(ErroDeNFe, match="idLote"):
            montar_enviNFe([nota_assinada(certificado)], id_lote="abc")

    def test_xml_que_nao_e_nfe_recusado(self) -> None:
        with pytest.raises(ErroDeNFe, match="espera elementos NFe"):
            montar_enviNFe([b'<?xml version="1.0"?><outra/>'])


class TestStatus:
    def test_consulta_valida_no_schema(self) -> None:
        schema = etree.XMLSchema(etree.parse(str(SCHEMAS / "consStatServ_v4.00.xsd")))
        requisicao = montar_consStatServ(uf="GO", ambiente="2")
        assert schema.validate(etree.fromstring(requisicao)), [
            e.message for e in list(schema.error_list)[:3]
        ]

    def test_uf_e_ambiente(self) -> None:
        doc = etree.fromstring(montar_consStatServ(uf="GO", ambiente="2"))
        assert doc.find("{*}cUF").text == "52"
        assert doc.find("{*}tpAmb").text == "2"
        assert doc.find("{*}xServ").text == "STATUS"

    def test_ambiente_invalido(self) -> None:
        with pytest.raises(ErroDeNFe, match="tpAmb"):
            montar_consStatServ(uf="GO", ambiente="9")

    def test_uf_desconhecida(self) -> None:
        with pytest.raises(ErroDeNFe, match="UF"):
            montar_consStatServ(uf="ZZ")

    def test_le_resposta_da_sefaz(self) -> None:
        resposta = (
            b'<?xml version="1.0"?><retConsStatServ versao="4.00" '
            b'xmlns="http://www.portalfiscal.inf.br/nfe"><tpAmb>2</tpAmb>'
            b"<verAplic>GO4.0</verAplic><cStat>107</cStat>"
            b"<xMotivo>Servico em Operacao</xMotivo><cUF>52</cUF>"
            b"<dhRecbto>2026-11-25T12:00:00-03:00</dhRecbto><tMed>1</tMed>"
            b"</retConsStatServ>"
        )
        dados = interpretar_retorno_status(resposta)
        assert dados["cStat"] == "107"
        assert "Operacao" in dados["xMotivo"]
        assert dados["tMed"] == "1"

    def test_resposta_que_nao_e_xml(self) -> None:
        with pytest.raises(ErroDeNFe, match="não é XML"):
            interpretar_retorno_status(b"nao sou xml")
