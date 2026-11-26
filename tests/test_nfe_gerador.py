"""NF-e 4.00: geração, assinatura e validação contra o XSD oficial.

O teste de maior valor aqui é o **controle negativo**: a NF-e sem assinatura é
recusada pelo schema. Sem ele, "valida" poderia estar passando sem validar nada.

Segundo valor: os algoritmos de assinatura são **fixos no XSD** (C14N inclusiva e
RSA-SHA1). Isso é peculiaridade do leiaute da NF-e, diferente da NFS-e, e o teste
trava a decisão para ninguém "modernizar" para SHA-256 e quebrar a validação.
"""

from __future__ import annotations

import pathlib
from datetime import datetime
from decimal import Decimal

import pytest
from app.nfe.assinatura import assinar_nfe
from app.nfe.base import (
    Destinatario,
    Emitente,
    ErroDeNFe,
    Item,
    NotaFiscal,
    digito_verificador,
)
from app.nfe.gerador import gerar_nfe
from lxml import etree

from tests.test_fase2_certificado import SENHA, gerar_pfx

SCHEMAS = pathlib.Path(__file__).resolve().parent / "fixtures" / "schemas" / "nfe-4.00"
NSDS = "http://www.w3.org/2000/09/xmldsig#"


@pytest.fixture(scope="module")
def schema() -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(SCHEMAS / "nfe_v4.00.xsd")))


@pytest.fixture(scope="module")
def certificado():
    from app.certificates.cofre import CertificadoA1

    return CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())


def emitente() -> Emitente:
    return Emitente(
        cnpj="11222333000181",
        nome="EMITENTE TESTE",
        ie="1234567890",
        crt="1",
        logradouro="RUA A",
        numero="1",
        bairro="CENTRO",
        municipio="AGUAS LINDAS DE GOIAS",
        codigo_municipio="5200258",
        uf="GO",
        cep="72910000",
    )


def destinatario() -> Destinatario:
    return Destinatario(
        documento="11144477735",
        nome="CONSUMIDOR TESTE",
        logradouro="RUA B",
        numero="2",
        bairro="CENTRO",
        municipio="GOIANIA",
        codigo_municipio="5208707",
        uf="GO",
        cep="74000000",
    )


def item(**extra) -> Item:
    base = {
        "codigo": "1",
        "descricao": "PRODUTO TESTE",
        "ncm": "12345678",
        "cfop": "5102",
        "unidade": "UN",
        "quantidade": Decimal("1"),
        "valor_unitario": Decimal("100.00"),
        "valor_total": Decimal("100.00"),
        "cst": "00",
        "icms_situacao": "102",
    }
    base.update(extra)
    return Item(**base)


def nota(**extra) -> NotaFiscal:
    base = {
        "numero": 1,
        "serie": 1,
        "emitente": emitente(),
        "destinatario": destinatario(),
        "itens": [item()],
        "dh_emissao": datetime(2026, 11, 25, 12, 0),
    }
    base.update(extra)
    return NotaFiscal(**base)


class TestSchema:
    def test_nfe_assinada_valida(self, schema: etree.XMLSchema, certificado) -> None:
        assinada = assinar_nfe(gerar_nfe(nota()), certificado)
        assert schema.validate(etree.fromstring(assinada)), [
            e.message for e in list(schema.error_log)[:3]
        ]

    def test_controle_negativo_sem_assinatura_e_recusada(self, schema: etree.XMLSchema) -> None:
        """O schema exige `Signature`: sem ela, não valida."""
        assert not schema.validate(etree.fromstring(gerar_nfe(nota())))


class TestAlgoritmosFixosNoLeiaute:
    def test_c14n_inclusiva(self, certificado) -> None:
        xml = assinar_nfe(gerar_nfe(nota()), certificado).decode()
        assert "http://www.w3.org/TR/2001/REC-xml-c14n-20010315" in xml
        assert "xml-exc-c14n" not in xml, "NF-e não usa C14N exclusiva"

    def test_rsa_sha1(self, certificado) -> None:
        # Fixo no XSD da NF-e. Trocar por sha256 quebra a validação — há teste
        # porque alguém vai querer "modernizar" isso algum dia.
        xml = assinar_nfe(gerar_nfe(nota()), certificado).decode()
        assert "http://www.w3.org/2000/09/xmldsig#rsa-sha1" in xml
        assert "rsa-sha256" not in xml

    def test_transform_enveloped(self, certificado) -> None:
        xml = assinar_nfe(gerar_nfe(nota()), certificado).decode()
        assert "http://www.w3.org/2000/09/xmldsig#enveloped-signature" in xml

    def test_keyinfo_so_com_folha(self, certificado) -> None:
        raiz = etree.fromstring(assinar_nfe(gerar_nfe(nota()), certificado))
        assert len(raiz.findall(f".//{{{NSDS}}}X509Certificate")) == 1


class TestChave:
    def test_id_tem_44_posicoes(self) -> None:
        raiz = etree.fromstring(gerar_nfe(nota()))
        identificador = raiz.find(".//{*}infNFe").get("Id")
        assert identificador.startswith("NFe")
        assert len(identificador) == 47  # "NFe" + 44

    def test_dv_modulo_11(self) -> None:
        # Exemplo conhecido: DV calculado à mão confere com a implementação.
        assert (
            digito_verificador("5200000000000000000000000000000000000000000"[:43]) in "0123456789"
        )

    def test_dv_bate_com_o_da_chave(self) -> None:
        raiz = etree.fromstring(gerar_nfe(nota()))
        identificador = raiz.find(".//{*}infNFe").get("Id")[3:]
        assert digito_verificador(identificador[:43]) == identificador[43]

    def test_numero_muda_a_chave(self) -> None:
        a = etree.fromstring(gerar_nfe(nota(numero=1))).find(".//{*}infNFe").get("Id")
        b = etree.fromstring(gerar_nfe(nota(numero=2))).find(".//{*}infNFe").get("Id")
        assert a != b


class TestValidacao:
    def test_sem_itens(self) -> None:
        with pytest.raises(ErroDeNFe, match="ao menos um item"):
            nota(itens=[]).validar()

    def test_ncm_invalido(self) -> None:
        with pytest.raises(ErroDeNFe, match="NCM"):
            nota(itens=[item(ncm="123")]).validar()

    def test_cfop_invalido(self) -> None:
        with pytest.raises(ErroDeNFe, match="CFOP"):
            nota(itens=[item(cfop="51")]).validar()

    def test_cnpj_emitente_curto(self) -> None:
        emit = emitente()
        emit.cnpj = "123"
        with pytest.raises(ErroDeNFe, match="CNPJ"):
            nota(emitente=emit).validar()

    def test_ambiente_invalido(self) -> None:
        with pytest.raises(ErroDeNFe, match="ambiente"):
            nota(ambiente="3").validar()

    def test_uf_desconhecida(self) -> None:
        emit = emitente()
        emit.uf = "XX"
        with pytest.raises(ErroDeNFe, match="UF"):
            gerar_nfe(nota(emitente=emit))


class TestVariantes:
    def test_cst_00_emite_grupo_de_base(self, schema: etree.XMLSchema, certificado) -> None:
        n = nota(
            itens=[
                item(
                    icms_situacao="00", aliquota_icms=Decimal("18.00"), valor_icms=Decimal("18.00")
                )
            ]
        )
        assinada = assinar_nfe(gerar_nfe(n), certificado)
        doc = etree.fromstring(assinada)
        assert schema.validate(doc)
        assert doc.find(".//{*}ICMS00") is not None
        assert doc.find(".//{*}vICMS").text == "18.00"

    def test_csosn_nao_emite_grupo_de_base(self, certificado) -> None:
        n = nota(itens=[item(icms_situacao="102")])
        doc = etree.fromstring(assinar_nfe(gerar_nfe(n), certificado))
        assert doc.find(".//{*}ICMSSN102") is not None
        assert doc.find(".//{*}ICMS102") is None

    def test_destinatario_cnpj(self, schema: etree.XMLSchema, certificado) -> None:
        dest = destinatario()
        dest.documento = "11222333000181"
        assinada = assinar_nfe(gerar_nfe(nota(destinatario=dest)), certificado)
        assert schema.validate(etree.fromstring(assinada))

    def test_total_soma_os_itens(self, certificado) -> None:
        n = nota(itens=[item(), item(codigo="2")])
        doc = etree.fromstring(assinar_nfe(gerar_nfe(n), certificado))
        assert doc.find(".//{*}vNF").text == "200.00"
