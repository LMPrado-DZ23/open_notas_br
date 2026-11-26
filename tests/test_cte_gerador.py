"""Gerador de CT-e: gera, assina e valida contra o schema oficial 4.00."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from app.certificates.cofre import CertificadoA1
from app.cte import ErroCTe, PapelTomador
from app.cte.gerador import DadosCTe, Parte, gerar, gerar_assinado
from lxml import etree

NS = "http://www.portalfiscal.inf.br/cte"
NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"


@pytest.fixture(scope="module")
def certificado() -> CertificadoA1:
    from tests.test_fase2_certificado import SENHA, gerar_pfx

    return CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())


def dados(**extra) -> DadosCTe:
    base = {
        "numero": 1,
        "serie": 1,
        "chave": "52" + "0" * 42,
        "emitente": Parte(nome="EMPRESA TESTE", cnpj="11222333000181", ie="123456789"),
        "destinatario": Parte(nome="DESTINO TESTE", cnpj="11222333000181"),
        "papel_tomador": PapelTomador.DESTINATARIO,
        "valor_total": Decimal("100.00"),
        "peso": Decimal("10.00"),
        "produto": "CARGA",
        "data_emissao": datetime(2026, 11, 26, 12, 0),
        "rntrc": "12345678",
        "chaves_documentos": ("52" + "1" * 42,),
    }
    base.update(extra)
    return DadosCTe(**base)


class TestGeracao:
    def test_cte_assinado_valida_contra_o_schema(self, certificado) -> None:
        # O teste que importa: o XML sai do gerador, é assinado e o SCHEMA OFICIAL aceita.
        xml = gerar_assinado(dados(), certificado)
        raiz = etree.fromstring(xml)
        assert etree.QName(raiz).localname == "CTe"
        assert raiz.find(f".//{{{NS_DSIG}}}Signature") is not None

    def test_estrutura_minima(self, certificado) -> None:
        raiz = etree.fromstring(gerar_assinado(dados(), certificado))
        inf = raiz.find(f"{{{NS}}}infCte")
        assert inf is not None
        assert inf.get("versao") == "4.00"
        for grupo in ("ide", "emit", "dest", "vPrest", "imp", "infCTeNorm"):
            assert inf.find(f"{{{NS}}}{grupo}") is not None, grupo

    def test_modal_rodoviario_com_rntrc(self, certificado) -> None:
        raiz = etree.fromstring(gerar_assinado(dados(), certificado))
        rntrc = raiz.find(f".//{{{NS}}}infModal/{{{NS}}}rodo/{{{NS}}}RNTRC")
        assert rntrc is not None and rntrc.text == "12345678"


class TestVariantesDeTomador:
    def test_destinatario_usa_toma3(self, certificado) -> None:
        raiz = etree.fromstring(gerar_assinado(dados(), certificado))
        toma3 = raiz.find(f".//{{{NS}}}ide/{{{NS}}}toma3")
        assert toma3 is not None
        assert toma3.find(f"{{{NS}}}toma").text == "3"

    def test_outros_usa_toma4_com_documento(self, certificado) -> None:
        xml = gerar_assinado(dados(papel_tomador=PapelTomador.OUTROS), certificado)
        raiz = etree.fromstring(xml)
        toma4 = raiz.find(f".//{{{NS}}}ide/{{{NS}}}toma4")
        assert toma4 is not None
        assert toma4.find(f"{{{NS}}}CNPJ") is not None


class TestRecusas:
    def test_sem_chave_de_documento_recusa(self, certificado) -> None:
        with pytest.raises(ValueError, match="documento de carga"):
            gerar_assinado(dados(chaves_documentos=()), certificado)

    def test_sem_rntrc_recusa(self, certificado) -> None:
        with pytest.raises(ValueError, match="RNTRC"):
            gerar_assinado(dados(rntrc=""), certificado)

    def test_chave_curta_recusa(self, certificado) -> None:
        with pytest.raises(ValueError, match="44"):
            gerar_assinado(dados(chave="123"), certificado)

    def test_chave_de_documento_invalida_recusa(self, certificado) -> None:
        with pytest.raises(ValueError, match="documento inválida"):
            gerar_assinado(dados(chaves_documentos=("curta",)), certificado)


class TestValidacaoIndependente:
    def test_xml_nao_assinado_e_recusado_pelo_schema(self) -> None:
        # Prova por que existe `gerar_assinado`: sem `Signature`, o schema recusa o CT-e.
        raiz = gerar(dados())
        xml = b'<?xml version="1.0" encoding="UTF-8"?>' + etree.tostring(raiz)
        with pytest.raises(ErroCTe):
            from app.cte import validar

            validar(xml)
