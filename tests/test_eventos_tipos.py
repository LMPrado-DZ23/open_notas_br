"""Os 16 tipos de evento, validados contra o XSD oficial.

O catálogo codifica estrutura (CONFIRMADO no schema), não significado de negócio.
O teste percorre os 16 tipos, monta o XML e valida contra o `pedRegEvento_v1.01.xsd`.

Isso prova o que dá para provar offline: a forma. Não prova que a SEFIN aceita cada
evento nem que o enquadramento escolhido está correto — isso é decisão do
contribuinte e depende de chamada real.
"""

from __future__ import annotations

import pathlib

import pytest
from app.nfse.eventos_tipos import (
    TIPOS_DO_CONTRIBUINTE,
    TIPOS_EVENTO,
    ErroDeEventoCatalogo,
    construir_evento,
    obter_tipo,
    validar_campo,
)
from lxml import etree

SCHEMAS = pathlib.Path(__file__).resolve().parent / "fixtures" / "schemas" / "nfse-1.01"
CHAVE = "355030" + "11222333000181" + "9" * 30
OUTRA_CHAVE = "355030" + "11222333000181" + "7" * 30
CNPJ = "11222333000181"
DH = "2026-11-25T16:30:00+00:00"
ID_EVENTO = "35503012" + "1" + "11222333000181" + "9" * 33
MOTIVO = "Descricao do evento com mais de quinze caracteres"


@pytest.fixture(scope="module")
def schema() -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(SCHEMAS / "pedRegEvento_v1.01.xsd")))


def campos_de_exemplo(codigo: str) -> dict[str, str]:
    """Valor válido por tipo de campo — senão o teste falharia pelo motivo errado."""
    exemplo = {
        "TSMotivo": MOTIVO,
        "TSCPF": "11144477735",
        "TSChaveNFSe": OUTRA_CHAVE,
        "TSNumProcAdmAnaliseFiscalCanc": "123456",
        "TSIdNumEvento": ID_EVENTO,
    }
    valores = {}
    for definicao in obter_tipo(codigo).campos:
        if definicao.tipo in exemplo:
            valores[definicao.nome] = exemplo[definicao.tipo]
        elif definicao.tipo.startswith("TSCod"):
            from app.nfse.eventos_tipos import RESTRICOES

            valores[definicao.nome] = str(RESTRICOES[definicao.tipo]["enum"][0])
        else:
            valores[definicao.nome] = "Descricao curta do evento"
    return valores


class TestCatalogo:
    def test_tem_os_16_tipos(self) -> None:
        assert len(TIPOS_EVENTO) == 16

    def test_codigos_tem_seis_digitos(self) -> None:
        assert all(len(c) == 6 and c.isdigit() for c in TIPOS_EVENTO)

    def test_grupo_tem_prefixo_e(self) -> None:
        assert obter_tipo("101101").grupo == "e101101"

    def test_tipo_inexistente_lista_os_reais(self) -> None:
        with pytest.raises(ErroDeEventoCatalogo, match="Disponíveis"):
            obter_tipo("999999")

    def test_subconjunto_do_contribuinte(self) -> None:
        assert all(c in TIPOS_EVENTO for c in TIPOS_DO_CONTRIBUINTE)


class TestTodosContraSchema:
    @pytest.mark.parametrize("codigo", sorted(TIPOS_EVENTO))
    def test_evento_valida_contra_o_xsd(self, schema: etree.XMLSchema, codigo: str) -> None:
        xml = construir_evento(
            codigo,
            chave=CHAVE,
            cnpj_autor=CNPJ,
            campos=campos_de_exemplo(codigo),
            ambiente="2",
            dh_evento=DH,
        )
        doc = etree.fromstring(xml)
        assert schema.validate(doc), [f"{e.message}" for e in list(schema.error_log)[:3]]

    @pytest.mark.parametrize("codigo", sorted(TIPOS_EVENTO))
    def test_id_do_pedido_tem_pre_e_59(self, codigo: str) -> None:
        xml = construir_evento(
            codigo,
            chave=CHAVE,
            cnpj_autor=CNPJ,
            campos=campos_de_exemplo(codigo),
            ambiente="2",
            dh_evento=DH,
        )
        identificador = etree.fromstring(xml).find(".//{*}infPedReg").get("Id")
        assert identificador.startswith("PRE")
        assert identificador == f"PRE{CHAVE}{codigo}"
        assert len(identificador) == 59


class TestXDescOficial:
    def test_x_desc_e_gerado_pelo_catalogo(self, schema: etree.XMLSchema) -> None:
        """`xDesc` não é texto livre: o schema enumera uma descrição por tipo.

        Deixar o chamador escrever produz recusa — então o catálogo fornece.
        """
        from app.nfse.eventos_tipos import X_DESC

        for codigo, esperado in X_DESC.items():
            xml = construir_evento(
                codigo,
                chave=CHAVE,
                cnpj_autor=CNPJ,
                campos=campos_de_exemplo(codigo),
                dh_evento=DH,
            )
            doc = etree.fromstring(xml)
            assert doc.find(".//{*}xDesc").text == esperado
            assert schema.validate(doc), [e.message for e in list(schema.error_log)[:2]]

    def test_x_desc_do_chamador_e_recusado(self) -> None:
        with pytest.raises(ErroDeEventoCatalogo, match="não tem os campos xDesc"):
            construir_evento(
                "101101",
                chave=CHAVE,
                cnpj_autor=CNPJ,
                campos={"xDesc": "texto inventado", "cMotivo": "1", "xMotivo": MOTIVO},
                dh_evento=DH,
            )


class TestValidacaoLocal:
    def test_campo_obrigatorio_ausente(self) -> None:
        with pytest.raises(ErroDeEventoCatalogo, match="exige os campos cMotivo"):
            construir_evento(
                "101101",
                chave=CHAVE,
                cnpj_autor=CNPJ,
                campos={"xMotivo": MOTIVO},
                dh_evento=DH,
            )

    def test_campo_desconhecido_recusado(self) -> None:
        with pytest.raises(ErroDeEventoCatalogo, match="não tem os campos"):
            construir_evento(
                "101101",
                chave=CHAVE,
                cnpj_autor=CNPJ,
                campos={"cMotivo": "1", "xMotivo": MOTIVO, "inventado": "y"},
                dh_evento=DH,
            )

    def test_motivo_curto_recusado_com_mensagem_util(self) -> None:
        with pytest.raises(ErroDeEventoCatalogo, match="ao menos 15"):
            validar_campo("xMotivo", "TSMotivo", "curto")

    def test_enum_invalido(self) -> None:
        with pytest.raises(ErroDeEventoCatalogo, match="aceita 1, 2, 9"):
            validar_campo("cMotivo", "TSCodJustCanc", "7")

    def test_cpf_com_letra_recusado(self) -> None:
        with pytest.raises(ErroDeEventoCatalogo, match="padrão"):
            validar_campo("CPFAgTrib", "TSCPF", "1114447773A")

    def test_data_com_z_recusada(self) -> None:
        # O leiaute não aceita 'Z' apesar do tipo se chamar TSDateTimeUTC.
        with pytest.raises(ErroDeEventoCatalogo, match="não aceita 'Z'"):
            construir_evento(
                "101101",
                chave=CHAVE,
                cnpj_autor=CNPJ,
                campos={"cMotivo": "1", "xMotivo": MOTIVO},
                dh_evento="2026-11-25T16:30:00Z",
            )

    def test_ambiente_invalido(self) -> None:
        with pytest.raises(ErroDeEventoCatalogo, match="tpAmb"):
            construir_evento(
                "101101",
                chave=CHAVE,
                cnpj_autor=CNPJ,
                campos={"cMotivo": "1", "xMotivo": MOTIVO},
                ambiente="3",
                dh_evento=DH,
            )

    def test_chave_invalida(self) -> None:
        with pytest.raises(ErroDeEventoCatalogo, match="chave"):
            construir_evento(
                "101101",
                chave="123",
                cnpj_autor=CNPJ,
                campos={"cMotivo": "1", "xMotivo": MOTIVO},
                dh_evento=DH,
            )

    def test_escaping(self, schema: etree.XMLSchema) -> None:
        xml = construir_evento(
            "101101",
            chave=CHAVE,
            cnpj_autor=CNPJ,
            campos={"cMotivo": "1", "xMotivo": 'Motivo com "aspas" & <tags>'},
            dh_evento=DH,
        )
        doc = etree.fromstring(xml)
        assert schema.validate(doc)
        assert doc.find(".//{*}xMotivo").text == 'Motivo com "aspas" & <tags>'


class TestSubstituicao:
    def test_exige_chave_substituta(self) -> None:
        with pytest.raises(ErroDeEventoCatalogo, match="chSubstituta"):
            construir_evento(
                "105102",
                chave=CHAVE,
                cnpj_autor=CNPJ,
                campos={"cMotivo": "01"},
                dh_evento=DH,
            )

    def test_com_chave_substituta_valida(self, schema: etree.XMLSchema) -> None:
        xml = construir_evento(
            "105102",
            chave=CHAVE,
            cnpj_autor=CNPJ,
            campos={"cMotivo": "01", "chSubstituta": OUTRA_CHAVE},
            dh_evento=DH,
        )
        assert schema.validate(etree.fromstring(xml))
