"""Cancelamento: pedido de evento validado contra o XSD oficial.

Dois erros que o schema pegou e que a leitura do nome do campo não pegava:

1. `infPedReg/@Id` é `PRE` + chave + tipo = **59** caracteres. Existe um segundo
   identificador, `EVT` + chave + tipo + nPedReg = 62 (`TSIdEvento`), que é do
   evento **já registrado** — usar `EVT` no pedido faz o schema recusar por
   `maxLength`.
2. `TSDateTimeUTC` **não aceita `Z`**: o pattern exige offset numérico
   (`+00:00`, `-03:00`). O nome do tipo induz ao erro.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime, timedelta, timezone

import pytest
from app.nfse.evento import (
    MOTIVOS_CANCELAMENTO,
    ErroDeEvento,
    PedidoCancelamento,
    assinar_pedido_evento,
    construir_pedido_evento,
    id_evento_registrado,
    id_pedido_evento,
)
from lxml import etree

from tests.test_fase2_certificado import SENHA, gerar_pfx

SCHEMAS = pathlib.Path(__file__).resolve().parent / "fixtures" / "schemas" / "nfse-1.01"
CHAVE = "355030" + "11222333000181" + "9" * 30
CNPJ = "11222333000181"


@pytest.fixture(scope="module")
def schema() -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(SCHEMAS / "pedRegEvento_v1.01.xsd")))


@pytest.fixture(scope="module")
def certificado():
    from app.certificates.cofre import CertificadoA1

    return CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())


def pedido(**extra) -> PedidoCancelamento:
    base = {
        "chave": CHAVE,
        "cnpj_autor": CNPJ,
        "c_motivo": "1",
        "x_motivo": "Cancelamento por erro na emissao do documento",
        "ambiente": "2",
        "dh_evento": datetime(2026, 11, 25, 16, 30, tzinfo=UTC),
    }
    base.update(extra)
    return PedidoCancelamento(**base)


class TestIdentificadores:
    def test_id_do_pedido_e_pre_com_59(self) -> None:
        identificador = id_pedido_evento(CHAVE, "101101")
        assert identificador.startswith("PRE")
        assert len(identificador) == 59
        assert id_pedido_evento(CHAVE, "101101") == identificador  # determinístico

    def test_id_do_evento_registrado_e_evt_com_62(self) -> None:
        identificador = id_evento_registrado(CHAVE, "101101", 1)
        assert identificador.startswith("EVT")
        assert len(identificador) == 62

    def test_chave_curta_recusada(self) -> None:
        with pytest.raises(ErroDeEvento, match="50 caracteres"):
            id_pedido_evento("123", "101101")

    def test_chave_fora_do_padrao_recusada(self) -> None:
        with pytest.raises(ErroDeEvento, match="padrão do leiaute"):
            id_pedido_evento("A" * 50, "101101")


class TestValidacaoLocal:
    def test_motivo_invalido_recusado(self) -> None:
        with pytest.raises(ErroDeEvento, match="cMotivo"):
            pedido(c_motivo="7").validar()

    def test_todos_os_motivos_do_schema_aceitos(self) -> None:
        for codigo in MOTIVOS_CANCELAMENTO:
            pedido(c_motivo=codigo).validar()

    def test_motivo_curto_recusado_antes_da_sefin(self) -> None:
        # 15 caracteres é o mínimo do schema: falhar aqui dá mensagem melhor.
        with pytest.raises(ErroDeEvento, match="15 a 255"):
            pedido(x_motivo="curto").validar()

    def test_motivo_longo_recusado(self) -> None:
        with pytest.raises(ErroDeEvento, match="15 a 255"):
            pedido(x_motivo="x" * 256).validar()

    def test_motivo_no_limite_aceito(self) -> None:
        pedido(x_motivo="x" * 255).validar()

    def test_ambiente_invalido(self) -> None:
        with pytest.raises(ErroDeEvento, match="tpAmb"):
            pedido(ambiente="3").validar()

    def test_cnpj_invalido(self) -> None:
        with pytest.raises(ErroDeEvento, match="CNPJAutor"):
            pedido(cnpj_autor="123").validar()


class TestXmlContraSchema:
    def test_pedido_valida(self, schema: etree.XMLSchema) -> None:
        doc = etree.fromstring(construir_pedido_evento(pedido()))
        assert schema.validate(doc), [e.message for e in list(schema.error_log)[:3]]

    def test_pedido_assinado_valida(self, schema: etree.XMLSchema, certificado) -> None:
        assinado = assinar_pedido_evento(construir_pedido_evento(pedido()), certificado)
        doc = etree.fromstring(assinado)
        assert schema.validate(doc), [e.message for e in list(schema.error_log)[:3]]

    def test_grupo_do_evento_e_e101101(self) -> None:
        doc = etree.fromstring(construir_pedido_evento(pedido()))
        nomes = {etree.QName(e.tag).localname for e in doc.iter()}
        assert "e101101" in nomes
        assert "chNFSe" in nomes

    def test_controle_negativo_id_com_evt_e_recusado(self, schema: etree.XMLSchema) -> None:
        """Prova que a validação não é vazia: com `EVT` o schema recusa."""
        xml = construir_pedido_evento(pedido()).replace(b'Id="PRE', b'Id="EVT')
        assert not schema.validate(etree.fromstring(xml))

    def test_controle_negativo_datetime_com_z_e_recusado(self, schema: etree.XMLSchema) -> None:
        """O schema exige offset; `Z` é recusado apesar do nome `TSDateTimeUTC`."""
        xml = construir_pedido_evento(pedido()).replace(b"+00:00<", b"Z<")
        assert not schema.validate(etree.fromstring(xml))

    def test_datetime_com_offset_local_valido(self, schema: etree.XMLSchema) -> None:
        # -03:00 (Brasília) também é aceito pelo pattern; o código normaliza para UTC.
        fuso = timezone(timedelta(hours=-3))
        doc = etree.fromstring(
            construir_pedido_evento(pedido(dh_evento=datetime(2026, 11, 25, 13, 30, tzinfo=fuso)))
        )
        assert schema.validate(doc)

    def test_datetime_sem_fuso_recusado(self) -> None:
        with pytest.raises(ErroDeEvento, match="fuso"):
            construir_pedido_evento(pedido(dh_evento=datetime(2026, 11, 25, 13, 30)))

    def test_escaping_no_motivo(self, schema: etree.XMLSchema) -> None:
        doc = etree.fromstring(
            construir_pedido_evento(pedido(x_motivo='Cancelamento por "erro" & falha <grave>'))
        )
        assert schema.validate(doc)
        texto = doc.find(".//{http://www.sped.fazenda.gov.br/nfse}xMotivo").text
        assert texto == 'Cancelamento por "erro" & falha <grave>'
