"""Fábrica de drivers: registro -> driver, com as invariantes de fonte e https."""

from __future__ import annotations

import pytest
from app.nfse.drivers import ErroDeDriver
from app.nfse.drivers_factory import MunicipioParaDriver, criar_driver

NS = "http://www.abrasf.org.br/nfse.xsd"
URL = "https://provedor.example/nfse"


class TransporteFalso:
    async def enviar(self, *, url: str, corpo: bytes, encoding: str) -> bytes:
        return b"<x/>"


def municipio(**extra) -> MunicipioParaDriver:
    base = {
        "codigo_ibge": "5208707",
        "provedor": "ginfes",
        "url": URL,
        "namespace": NS,
        "fonte_url": "https://www.goiania.go.gov.br/nfse/manual.pdf",
    }
    base.update(extra)
    return MunicipioParaDriver(**base)


class TestMontagem:
    def test_monta_driver_com_a_configuracao_do_registro(self) -> None:
        driver = criar_driver(municipio(), transporte=TransporteFalso())
        assert driver.nome == "ginfes"

    def test_encoding_do_registro_chega_ao_driver(self) -> None:
        driver = criar_driver(municipio(encoding="ISO-8859-1"), transporte=TransporteFalso())
        assert driver._conf.encoding == "ISO-8859-1"

    def test_versao_de_soap_do_registro_chega_ao_driver(self) -> None:
        driver = criar_driver(municipio(versao_soap="1.1"), transporte=TransporteFalso())
        assert driver._conf.versao_soap == "1.1"


class TestGuardaDeFonte:
    def test_sem_url_recusa_com_motivo(self) -> None:
        with pytest.raises(ErroDeDriver, match="sem URL"):
            criar_driver(municipio(url=None), transporte=TransporteFalso())

    def test_sem_fonte_url_recusa(self) -> None:
        # URL sem fonte é chute; R8 proíbe inventar endereço fiscal.
        with pytest.raises(ErroDeDriver, match="sem fonte registrada"):
            criar_driver(municipio(fonte_url=None), transporte=TransporteFalso())

    def test_http_e_recusado(self) -> None:
        with pytest.raises(ErroDeDriver, match="https"):
            criar_driver(municipio(url="http://inseguro.example/x"), transporte=TransporteFalso())


class TestProvedores:
    def test_provedor_sem_motor_recusa_com_motivo(self) -> None:
        with pytest.raises(ErroDeDriver, match="não implementado"):
            criar_driver(municipio(provedor="provedor_inexistente"), transporte=TransporteFalso())

    def test_nacional_rest_nao_usa_o_motor_abrasf(self) -> None:
        with pytest.raises(ErroDeDriver, match="adaptador nacional"):
            criar_driver(municipio(provedor="nacional_rest"), transporte=TransporteFalso())


class TestValidacao:
    def test_ibge_com_sete_digitos(self) -> None:
        with pytest.raises(ValueError, match="IBGE"):
            municipio(codigo_ibge="520870")

    def test_ibge_nao_numerico(self) -> None:
        with pytest.raises(ValueError, match="IBGE"):
            municipio(codigo_ibge="52087OA")
