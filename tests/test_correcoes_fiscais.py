"""Três defeitos graves que os testes de cobertura revelaram, corrigidos aqui.

1. **`dhEmi` deslocado** — a NF-e convertia para UTC **e** rotulava `-03:00` (3 h à frente); CT-e e
   MDF-e formatavam sem converter e rotulavam `-03:00`. Data de emissão fiscal errada é rejeição e, na
   virada do dia, nota com data que não existe. Regra única em `app/core/fiscal.py`.
2. **`<infAdic>` duplicado** — a NF-e com informação adicional gerava dois elementos, e o XSD
   (`maxOccurs=1`) recusa **toda** NF-e com texto adicional.
3. **Raízes ICP-Brasil nunca carregadas** — `_carregar_raizes_do_sistema` existia e não era chamada por
   `ssl_context()`: no Windows o handshake com SVRS/SEFAZ-SP voltava a falhar sem que ninguém tivesse
   mexido no certificado.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from app.certificates import cofre as modulo_cofre
from app.core.fiscal import dh_emi
from app.nfe.assinatura import assinar_nfe
from app.nfe.gerador import gerar_nfe
from lxml import etree

from tests.test_nfe_gerador import nota

SCHEMAS = pathlib.Path(__file__).resolve().parent / "fixtures" / "schemas" / "nfe-4.00"


class TestDhEmi:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            # Instante UTC 15:00 = 12:00 em Brasília. Antes saía 15:00-03:00.
            (datetime(2026, 11, 25, 15, 0, tzinfo=UTC), "2026-11-25T12:00:00-03:00"),
            # Já em Brasília: não pode mudar.
            (
                datetime(2026, 11, 25, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
                "2026-11-25T12:00:00-03:00",
            ),
            # Sem fuso: convenção do projeto é que já está em Brasília.
            (datetime(2026, 11, 25, 12, 0), "2026-11-25T12:00:00-03:00"),
        ],
    )
    def test_instante_preservado(self, entrada: datetime, esperado: str) -> None:
        assert dh_emi(entrada) == esperado

    def test_virada_do_dia_nao_muda_a_data(self) -> None:
        """01:00 UTC do dia 26 ainda é dia 25 em Brasília — e o XML precisa dizer isso."""
        assert dh_emi(datetime(2026, 11, 26, 1, 0, tzinfo=UTC)) == "2026-11-25T22:00:00-03:00"

    def test_gerador_usa_o_instante_certo(self) -> None:
        xml = gerar_nfe(nota(dh_emissao=datetime(2026, 11, 25, 15, 0, tzinfo=UTC)))

        assert b"<dhEmi>2026-11-25T12:00:00-03:00</dhEmi>" in xml


class TestInfAdic:
    def test_informacao_adicional_gera_um_unico_infadic(self) -> None:
        xml = gerar_nfe(nota(informacoes_adicionais="PEDIDO 8842"))
        raiz = etree.fromstring(xml)

        encontrados = [e for e in raiz.iter() if etree.QName(e).localname == "infAdic"]
        assert len(encontrados) == 1, "dois infAdic violam o XSD (maxOccurs=1)"
        assert b"PEDIDO 8842" in xml

    def test_nfe_com_info_adicional_passa_no_xsd(self) -> None:
        """O teste que faltava: gerar com informação adicional **e** validar contra o leiaute."""
        from app.certificates.cofre import CertificadoA1

        from tests.test_fase2_certificado import SENHA, gerar_pfx

        certificado = CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())
        schema = etree.XMLSchema(etree.parse(str(SCHEMAS / "nfe_v4.00.xsd")))
        assinada = assinar_nfe(gerar_nfe(nota(informacoes_adicionais="PEDIDO 8842")), certificado)

        assert schema.validate(etree.fromstring(assinada)), [
            e.message for e in list(schema.error_log)[:3]
        ]


class TestRaizesDoSistema:
    def test_ssl_context_carrega_as_raizes(self, monkeypatch) -> None:
        """A função existia e nunca era chamada: no Windows o handshake com ICP-Brasil falhava."""
        chamadas: list[object] = []
        monkeypatch.setattr(
            modulo_cofre, "_carregar_raizes_do_sistema", lambda ctx: chamadas.append(ctx) or 0
        )

        _certificado_de_teste().ssl_context()

        assert chamadas, "_carregar_raizes_do_sistema precisa ser chamada pelo ssl_context"

    def test_contexto_minimo_tls_1_2(self) -> None:
        import ssl

        contexto = _certificado_de_teste().ssl_context()

        assert contexto.minimum_version >= ssl.TLSVersion.TLSv1_2


def _certificado_de_teste():
    from app.certificates.cofre import CertificadoA1

    from tests.test_fase2_certificado import SENHA, gerar_pfx

    return CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())
