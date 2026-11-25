"""Correções descobertas na primeira emissão real contra a SEFIN.

Cada teste aqui existe por causa de uma rejeição observada na Produção Restrita.
Sem eles, alguém "simplifica" o assinador de volta e a emissão volta a falhar com
um código que não aponta para a causa.
"""

from __future__ import annotations

import pathlib
from datetime import datetime
from decimal import Decimal

import pytest
from app.db.models.enums import AmbienteFiscal
from app.nfse.constants import FUSO_BR
from app.nfse.dps import DpsInput, Prestador, Tomador, dps_para_bytes
from app.nfse.errors import orientacao
from app.nfse.signer import assinar_dps, verificar
from lxml import etree

from tests.test_fase2_certificado import SENHA, gerar_pfx

NSDS = "http://www.w3.org/2000/09/xmldsig#"
SCHEMAS = pathlib.Path(__file__).resolve().parent / "fixtures" / "schemas" / "nfse-1.01"


@pytest.fixture(scope="module")
def certificado():
    from app.certificates.cofre import CertificadoA1

    return CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())


def dps_de_teste(n: int = 1) -> bytes:
    return dps_para_bytes(
        DpsInput(
            ambiente=AmbienteFiscal.HOMOLOGACAO,
            c_mun_emissor="3550308",
            serie=1,
            n_dps=n,
            dh_emi=datetime(2026, 11, 25, 18, 0, tzinfo=FUSO_BR),
            prestador=Prestador(documento="11222333000181"),
            tomador=Tomador(nome="Tomador", documento="11144477735"),
            c_trib_nac="010701",
            x_desc_serv="Servico de teste",
            valor=Decimal("10.00"),
        )
    )


class TestKeyInfoSoComFolha:
    def test_um_unico_certificado_no_keyinfo(self, certificado) -> None:
        """A SEFIN recusou (E0714) quando enviamos a cadeia inteira.

        Nosso A1 ICP-Brasil traz 4 certificados. O documento válido de referência
        também traz um único X509Certificate.
        """
        assinada = assinar_dps(dps_de_teste(), certificado)
        raiz = etree.fromstring(assinada)
        certificados = raiz.findall(f".//{{{NSDS}}}X509Certificate")
        assert len(certificados) == 1

    def test_assinatura_continua_valida(self, certificado) -> None:
        assinada = assinar_dps(dps_de_teste(2), certificado)
        assert verificar(assinada, certificado) is True

    def test_dps_assinada_ainda_valida_no_schema(self, certificado) -> None:
        schema = etree.XMLSchema(etree.parse(str(SCHEMAS / "DPS_v1.01.xsd")))
        assinada = assinar_dps(dps_de_teste(3), certificado)
        assert schema.validate(etree.fromstring(assinada))


class TestDeclaracaoXml:
    def test_declaracao_com_aspas_duplas(self, certificado) -> None:
        """E1229: o validador procura o literal `encoding="UTF-8"`."""
        assinada = assinar_dps(dps_de_teste(4), certificado)
        assert assinada.startswith(b'<?xml version="1.0" encoding="UTF-8"?>')

    def test_dps_gerada_ja_tem_declaracao(self) -> None:
        assert dps_de_teste(5).startswith(b'<?xml version="1.0" encoding="UTF-8"?>')


class TestCanonicalizacao:
    def test_exclusive_c14n_com_comentarios(self, certificado) -> None:
        """A referência válida usa `xml-exc-c14n#WithComments`, não a versão seca."""
        xml = assinar_dps(dps_de_teste(6), certificado).decode()
        assert "http://www.w3.org/2001/10/xml-exc-c14n#WithComments" in xml


class TestIdDaDps:
    def test_id_tem_45_posicoes(self) -> None:
        """Regra do XSD: DPS + município(7) + tipo(1) + inscrição(14) + série(5) + número(15)."""
        raiz = etree.fromstring(dps_de_teste(7))
        identificador = raiz.find(".//{*}infDPS").get("Id")
        assert len(identificador) == 45
        assert identificador.startswith("DPS3550308")
        assert identificador.endswith("000000000000007")

    def test_id_muda_com_o_numero(self) -> None:
        # Id inconsistente com os campos gera E0004 na SEFIN.
        a = etree.fromstring(dps_de_teste(8)).find(".//{*}infDPS").get("Id")
        b = etree.fromstring(dps_de_teste(9)).find(".//{*}infDPS").get("Id")
        assert a != b


class TestOrientacao:
    @pytest.mark.parametrize("codigo", ["E0312", "E0008", "E0714", "E1229", "E2401", "E2404"])
    def test_codigos_reais_tem_orientacao(self, codigo: str) -> None:
        dica = orientacao(codigo)
        assert dica and len(dica) > 40

    def test_codigo_desconhecido_nao_inventa(self) -> None:
        assert orientacao("X9999") is None

    def test_normaliza_maiuscula(self) -> None:
        assert orientacao("e0312") == orientacao("E0312")

    def test_sem_codigo(self) -> None:
        assert orientacao(None) is None

    def test_e0312_aponta_para_municipio_nao_aderente(self) -> None:
        assert "município não aderiu" in orientacao("E0312")

    def test_e0714_lista_as_tres_causas(self) -> None:
        dica = orientacao("E0714")
        assert "KeyInfo" in dica and "declaração" in dica and "c14n" in dica.lower()
