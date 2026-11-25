"""Testes do DANFE A4 e das etiquetas de volume.

A etiqueta é o alvo principal: ela vai colada na caixa e é o que o conferente lê.
Se o índice do volume estiver errado, falta caixa no destino e ninguém percebe
aqui. Por isso o teste verifica cada etiqueta individualmente, não só o PDF.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from app.danfe import gerar
from app.danfe.a4 import extrair_danfe_a4, gerar_danfe_a4
from app.danfe.etiquetas import (
    codigo_do_volume,
    extrair_etiquetas,
    gerar_etiquetas,
)
from pypdf import PdfReader

from tests.construir import nfe

VOLUMES = [
    {"qVol": "2", "esp": "CAIXA", "pesoL": "12.500", "pesoB": "13.200", "marca": "ACME"},
    {"qVol": "1", "esp": "PALLET", "pesoL": "80.000", "pesoB": "85.500"},
]


def texto_do_pdf(pdf: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages)


@pytest.fixture(scope="module")
def xml_com_volumes() -> bytes:
    return nfe(volumes=VOLUMES)


@pytest.fixture(scope="module")
def xml_sem_volumes() -> bytes:
    return nfe()


class TestExtracaoEtiquetas:
    def test_destinatario_e_remetente(self, xml_com_volumes: bytes) -> None:
        dados = extrair_etiquetas(xml_com_volumes)
        assert dados.emitente_nome == "Empresa Exemplo LTDA"
        assert dados.destinatario_nome == "Cliente Exemplo SA"
        assert "Rua Exemplo" in dados.destinatario_endereco
        assert dados.destinatario_cep == "01001-000"

    def test_numero_e_chave(self, xml_com_volumes: bytes) -> None:
        dados = extrair_etiquetas(xml_com_volumes)
        assert dados.numero_nota == "123"
        assert len(dados.chave) == 44

    def test_volumes_do_xml(self, xml_com_volumes: bytes) -> None:
        # VOLUMES declara qVol=2 (CAIXA) e qVol=1 (PALLET): 2 + 1 = 3 etiquetas.
        # qVol é quantidade de volumes do grupo, não um volume.
        dados = extrair_etiquetas(xml_com_volumes)
        assert len(dados.volumes) == 3
        assert [v.especie for v in dados.volumes] == ["CAIXA", "CAIXA", "PALLET"]
        assert dados.volumes[0].peso_bruto == "13,200"
        assert dados.volumes[2].peso_bruto == "85,500"
        assert all(v.total == 3 for v in dados.volumes)

    def test_sem_volumes_usa_quantidade_informada(self, xml_sem_volumes: bytes) -> None:
        dados = extrair_etiquetas(xml_sem_volumes, quantidade_volumes=3)
        assert len(dados.volumes) == 3
        assert [v.indice for v in dados.volumes] == [1, 2, 3]
        assert all(v.peso_bruto == "" for v in dados.volumes), "peso não pode ser inventado"

    def test_pedido_maior_que_xml_nao_repetir_peso(self, xml_com_volumes: bytes) -> None:
        dados = extrair_etiquetas(xml_com_volumes, quantidade_volumes=5)
        assert len(dados.volumes) == 5
        # As 4ª e 5ª não existem no XML: saem sem peso, em vez de clonar o da 1ª.
        assert dados.volumes[3].peso_bruto == ""
        assert dados.volumes[4].peso_bruto == ""

    def test_pedido_menor_trunca(self, xml_com_volumes: bytes) -> None:
        dados = extrair_etiquetas(xml_com_volumes, quantidade_volumes=1)
        assert len(dados.volumes) == 1
        assert dados.volumes[0].total == 1

    def test_coleta_vem_da_emissao(self, xml_com_volumes: bytes) -> None:
        dados = extrair_etiquetas(xml_com_volumes)
        assert dados.coleta == "15/01/2025 10:30"


class TestCodigoDoVolume:
    def test_formato(self, xml_com_volumes: bytes) -> None:
        dados = extrair_etiquetas(xml_com_volumes)
        codigo = codigo_do_volume(dados, dados.volumes[0])
        # <prefixo 5 letras><nota 7 dígitos>V<volume>
        assert codigo == "EMPRE0000123V1"

    def test_deterministico(self, xml_com_volumes: bytes) -> None:
        dados = extrair_etiquetas(xml_com_volumes)
        assert codigo_do_volume(dados, dados.volumes[1]) == codigo_do_volume(
            dados, dados.volumes[1]
        )

    def test_indice_muda_o_codigo(self, xml_com_volumes: bytes) -> None:
        dados = extrair_etiquetas(xml_com_volumes)
        assert codigo_do_volume(dados, dados.volumes[0]) != codigo_do_volume(
            dados, dados.volumes[1]
        )


class TestPdfEtiquetas:
    def test_gera_pdf_valido(self, xml_com_volumes: bytes) -> None:
        pdf = gerar_etiquetas(extrair_etiquetas(xml_com_volumes))
        assert pdf.startswith(b"%PDF")

    def test_duas_etiquetas_por_pagina(self, xml_com_volumes: bytes) -> None:
        # 3 volumes, 2 por folha -> 2 páginas.
        pdf = gerar_etiquetas(extrair_etiquetas(xml_com_volumes))
        assert len(PdfReader(BytesIO(pdf)).pages) == 2

    def test_pagina_extra_para_muitos_volumes(self, xml_sem_volumes: bytes) -> None:
        pdf = gerar_etiquetas(extrair_etiquetas(xml_sem_volumes, quantidade_volumes=5))
        assert len(PdfReader(BytesIO(pdf)).pages) >= 2

    def test_campos_da_imagem_de_referencia(self, xml_com_volumes: bytes) -> None:
        pdf = gerar_etiquetas(extrair_etiquetas(xml_com_volumes))
        texto = texto_do_pdf(pdf)
        assert "Volume 1/3" in texto
        assert "Volume 2/3" in texto
        assert "PESO (kg)" in texto
        assert "NOTA FISCAL" in texto
        assert "COLETA" in texto
        assert "DESTINATÁRIO" in texto
        assert "REMETENTE" in texto

    def test_conteudo_da_etiqueta(self, xml_com_volumes: bytes) -> None:
        pdf = gerar_etiquetas(extrair_etiquetas(xml_com_volumes))
        texto = texto_do_pdf(pdf)
        assert "Cliente Exemplo SA" in texto
        assert "Empresa Exemplo LTDA" in texto
        assert "13,200" in texto, "peso do XML precisa aparecer"
        assert "01001-000" in texto
        assert "EMPRE0000123V1" in texto

    def test_avisa_campos_ausentes(self) -> None:
        from tests.construir import sem_campo

        xml = sem_campo(nfe(volumes=VOLUMES), "NFe/infNFe/dest/xNome")
        dados = extrair_etiquetas(xml)
        assert "destinatario_nome" in dados.ausentes
        assert "Campos não encontrados" in texto_do_pdf(gerar_etiquetas(dados))


class TestDanfeA4:
    def test_extrai_cabecalho(self, xml_com_volumes: bytes) -> None:
        dados = extrair_danfe_a4(xml_com_volumes)
        assert dados.numero == "123"
        assert dados.serie == "1"
        assert dados.modelo == "55"
        assert dados.operacao == "1-SAÍDA"
        assert len(dados.chave) == 44
        assert dados.protocolo == "135250000000001"

    def test_extrai_partes(self, xml_com_volumes: bytes) -> None:
        dados = extrair_danfe_a4(xml_com_volumes)
        assert dados.emitente_documento == "11.222.333/0001-81"
        assert dados.destinatario_nome == "Cliente Exemplo SA"
        assert dados.emitente_municipio_uf

    def test_extrai_totais(self, xml_com_volumes: bytes) -> None:
        dados = extrair_danfe_a4(xml_com_volumes)
        assert dados.valor_total == "1.000,00"
        assert dados.valor_produtos

    def test_extrai_itens(self, xml_com_volumes: bytes) -> None:
        dados = extrair_danfe_a4(xml_com_volumes)
        assert len(dados.itens) == 1
        assert dados.itens[0].descricao
        assert dados.itens[0].cfop == "5102"

    def test_extrai_volumes_e_frete(self, xml_com_volumes: bytes) -> None:
        dados = extrair_danfe_a4(xml_com_volumes)
        assert len(dados.volumes) == 2
        assert dados.modalidade_frete.startswith("9-")

    def test_pdf_valido_e_contem_campos(self, xml_com_volumes: bytes) -> None:
        pdf = gerar_danfe_a4(extrair_danfe_a4(xml_com_volumes))
        assert pdf.startswith(b"%PDF")
        texto = texto_do_pdf(pdf)
        assert "DANFE" in texto
        assert "Empresa Exemplo LTDA" in texto
        assert "Cliente Exemplo SA" in texto
        assert "1.000,00" in texto
        assert "CÁLCULO DO IMPOSTO" in texto
        assert "TRANSPORTADOR" in texto
        assert "A VALIDAR" in texto

    def test_paisagem(self, xml_com_volumes: bytes) -> None:
        pdf = gerar_danfe_a4(extrair_danfe_a4(xml_com_volumes))
        pagina = PdfReader(BytesIO(pdf)).pages[0]
        assert float(pagina.mediabox.width) > float(pagina.mediabox.height)


class TestDispatch:
    def test_danfe_a4_pelo_registro(self, xml_com_volumes: bytes) -> None:
        assert gerar("nfe", xml_com_volumes, formato="danfe").startswith(b"%PDF")

    def test_etiquetas_pelo_registro(self, xml_com_volumes: bytes) -> None:
        pdf = gerar("nfe", xml_com_volumes, formato="etiquetas")
        assert pdf.startswith(b"%PDF")
        assert "Volume 1/3" in texto_do_pdf(pdf)

    def test_formatos_registrados(self) -> None:
        from app.danfe import disponiveis

        formatos = {(t.documento, t.formato) for t in disponiveis()}
        assert ("nfe", "danfe") in formatos
        assert ("nfe", "etiquetas") in formatos
        assert ("nfe", "danfe_simplificado") in formatos
