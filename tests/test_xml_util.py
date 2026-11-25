"""Testes das utilidades de XML: segurança do parse e navegação sem namespace."""

from __future__ import annotations

from decimal import Decimal

import pytest

from notasbr.erros import ArquivoGrandeDemais, XmlInvalido
from notasbr.xml_util import (
    caminho_de,
    decimal,
    dinheiro,
    filhos,
    mapa_de_pais,
    namespace,
    navegar,
    parse_seguro,
    texto,
    texto_em,
)

XML_SIMPLES = b"""<?xml version="1.0" encoding="UTF-8"?>
<a xmlns="urn:teste"><b><c>valor</c><c>outro</c></b><b><c>terceiro</c></b></a>"""


class TestParseSeguro:
    def test_le_xml_com_namespace_default(self) -> None:
        raiz = parse_seguro(XML_SIMPLES)
        assert namespace(raiz.tag) == "urn:teste"
        assert texto_em(raiz, "b/c") == "valor"

    def test_recusa_doctype(self) -> None:
        payload = b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>'
        with pytest.raises(XmlInvalido, match="DTD"):
            parse_seguro(payload)

    def test_recusa_entidade(self) -> None:
        with pytest.raises(XmlInvalido):
            parse_seguro(b"<!ENTITY lol 'lol'><a/>")

    def test_recusa_conteudo_vazio(self) -> None:
        with pytest.raises(XmlInvalido, match="vazio"):
            parse_seguro(b"   ")

    def test_recusa_xml_malformado(self) -> None:
        with pytest.raises(XmlInvalido, match="mal formado"):
            parse_seguro(b"<a><b></a>")

    def test_recusa_acima_do_limite(self) -> None:
        with pytest.raises(ArquivoGrandeDemais, match="limite"):
            parse_seguro(XML_SIMPLES, limite=10)


class TestNavegacao:
    def test_navegar_por_nomes_locais(self) -> None:
        raiz = parse_seguro(XML_SIMPLES)
        assert texto(navegar(raiz, "b/c")) == "valor"

    def test_navegar_caminho_inexistente(self) -> None:
        raiz = parse_seguro(XML_SIMPLES)
        assert navegar(raiz, "b/z") is None
        assert navegar(None, "b") is None

    def test_filhos_repetidos(self) -> None:
        raiz = parse_seguro(XML_SIMPLES)
        assert len(filhos(raiz, "b")) == 2
        assert [texto(c) for c in filhos(raiz, "b")] == [None, None]

    def test_texto_normaliza_espacos(self) -> None:
        raiz = parse_seguro(b"<a><b>  com   espaco  </b><c>   </c></a>")
        assert texto_em(raiz, "b") == "com espaco"
        assert texto_em(raiz, "c") is None  # só espaço vira None


class TestCaminhoDe:
    def test_marca_irmaos_repetidos(self) -> None:
        raiz = parse_seguro(XML_SIMPLES)
        pais = mapa_de_pais(raiz)
        segundos_b = filhos(raiz, "b")
        alvo = navegar(segundos_b[1], "c")
        assert alvo is not None
        # a segunda ocorrência de <b> recebe índice
        assert caminho_de(raiz, alvo, pais) == "a/b[2]/c"

    def test_raiz_tem_caminho_proprio(self) -> None:
        raiz = parse_seguro(XML_SIMPLES)
        pais = mapa_de_pais(raiz)
        assert caminho_de(raiz, raiz, pais) == "a"


class TestDecimal:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("1234.56", Decimal("1234.56")),
            ("1234,56", Decimal("1234.56")),
            ("0", Decimal("0")),
            ("-10.5", Decimal("-10.5")),
        ],
    )
    def test_converte(self, entrada: str, esperado: Decimal) -> None:
        assert decimal(entrada) == esperado

    @pytest.mark.parametrize("entrada", [None, "", "abc", "1.2.3"])
    def test_devolve_none(self, entrada: str | None) -> None:
        assert decimal(entrada) is None

    def test_dinheiro_arredonda_duas_casas(self) -> None:
        assert dinheiro(Decimal("10.005")) == "10.01"
        assert dinheiro(Decimal("10")) == "10.00"
        assert dinheiro(None) is None
