"""Gerador de MDF-e: gera, assina e valida contra o schema oficial 3.00."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from app.certificates.cofre import CertificadoA1
from app.mdfe import ErroMDFe, validar
from app.mdfe.gerador import (
    DadosMDFe,
    Descarga,
    Emitente,
    MunicipioCarregamento,
    gerar,
    gerar_assinado,
)
from lxml import etree

NS = "http://www.portalfiscal.inf.br/mdfe"
NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"


@pytest.fixture(scope="module")
def certificado() -> CertificadoA1:
    from tests.test_fase2_certificado import SENHA, gerar_pfx

    return CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())


def dados(**extra) -> DadosMDFe:
    base = {
        "numero": 1,
        "serie": 1,
        "chave": "52" + "0" * 42,
        "emitente": Emitente(
            cnpj="11222333000181",
            nome="EMPRESA TESTE",
            ie="123456789",
            municipio_ibge="5208707",
            municipio="GOIANIA",
            uf="GO",
        ),
        "uf_inicio": "GO",
        "uf_fim": "GO",
        "municipios_carregamento": (MunicipioCarregamento("5208707", "GOIANIA"),),
        "valor_carga": Decimal("1000.00"),
        "peso": Decimal("10.00"),
        "data_emissao": datetime(2026, 11, 26, 12, 0),
        "descargas": (Descarga("5208707", "GOIANIA", ("52" + "1" * 42,)),),
    }
    base.update(extra)
    return DadosMDFe(**base)


class TestGeracao:
    def test_mdfe_assinado_valida_contra_o_schema(self, certificado) -> None:
        xml = gerar_assinado(dados(), certificado)
        raiz = etree.fromstring(xml)
        assert etree.QName(raiz).localname == "MDFe"
        assert raiz.find(f".//{{{NS_DSIG}}}Signature") is not None

    def test_estrutura_obrigatoria(self, certificado) -> None:
        raiz = etree.fromstring(gerar_assinado(dados(), certificado))
        inf = raiz.find(f"{{{NS}}}infMDFe")
        for grupo in ("ide", "emit", "infModal", "infDoc", "tot"):
            assert inf.find(f"{{{NS}}}{grupo}") is not None, grupo

    def test_municipio_de_carregamento_e_descarga(self, certificado) -> None:
        raiz = etree.fromstring(gerar_assinado(dados(), certificado))
        carrega = raiz.find(f".//{{{NS}}}infMunCarrega/{{{NS}}}cMunCarrega")
        descarga = raiz.find(f".//{{{NS}}}infMunDescarga/{{{NS}}}cMunDescarga")
        assert carrega is not None and carrega.text == "5208707"
        assert descarga is not None and descarga.text == "5208707"


class TestRecusas:
    def test_sem_descarga_recusa(self, certificado) -> None:
        with pytest.raises(ValueError, match="descarga"):
            gerar_assinado(dados(descargas=()), certificado)

    def test_descarga_sem_chave_recusa(self, certificado) -> None:
        with pytest.raises(ValueError, match="chave de NF-e"):
            gerar_assinado(dados(descargas=(Descarga("5208707", "GOIANIA", ()),)), certificado)

    def test_chave_curta_recusa(self, certificado) -> None:
        with pytest.raises(ValueError, match="44"):
            gerar_assinado(dados(chave="123"), certificado)

    def test_sem_municipio_de_carregamento_recusa(self, certificado) -> None:
        with pytest.raises(ValueError, match="carregamento"):
            gerar_assinado(dados(municipios_carregamento=()), certificado)


class TestValidacaoIndependente:
    def test_mdfe_nao_assinado_e_recusado(self) -> None:
        xml = b'<?xml version="1.0" encoding="UTF-8"?>' + etree.tostring(gerar(dados()))
        with pytest.raises(ErroMDFe):
            validar(xml)
