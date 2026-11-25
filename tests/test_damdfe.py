"""Testes do DAMDFE (MDF-e).

O MDF-e é o documento com **menor** grau de confiança de leiaute neste projeto:
não há XSD dele na base de referência (NF-e e CT-e têm). Por isso os testes
fixam o que é verificável — extração, campos obrigatórios, aviso de ausentes e
o próprio aviso de leiaute no PDF — em vez de fingir validação estrutural.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from app.danfe import disponiveis, gerar
from app.danfe.mdfe import extrair_damdfe, gerar_damdfe
from pypdf import PdfReader

from tests.construir import mdfe


def texto(pdf: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages)


@pytest.fixture(scope="module")
def xml_mdfe() -> bytes:
    return mdfe()


class TestExtracao:
    def test_identificacao(self, xml_mdfe: bytes) -> None:
        dados = extrair_damdfe(xml_mdfe)
        assert dados.numero == "77"
        assert dados.serie == "1"
        assert dados.modelo == "58"
        assert len(dados.chave) == 44
        assert dados.protocolo == "135250000000003"
        assert dados.modal == "1-Rodoviário"

    def test_emitente(self, xml_mdfe: bytes) -> None:
        dados = extrair_damdfe(xml_mdfe)
        assert dados.emitente_nome == "Transportadora Exemplo LTDA"
        assert dados.emitente_documento == "11.222.333/0001-81"
        assert dados.emitente_municipio_uf

    def test_percurso(self, xml_mdfe: bytes) -> None:
        dados = extrair_damdfe(xml_mdfe)
        assert dados.uf_inicio == "SP"
        assert dados.uf_fim == "RJ"
        assert dados.municipios_carregamento == ["Sao Paulo"]
        assert dados.municipios_descarga == ["Rio de Janeiro"]
        assert dados.ufs_percurso == ["MG"]

    def test_modal_rodoviario(self, xml_mdfe: bytes) -> None:
        dados = extrair_damdfe(xml_mdfe)
        assert dados.placa == "ABC1D23"
        assert dados.tara == "8500"
        assert dados.capacidade_kg == "25000"

    def test_documentos_e_totais(self, xml_mdfe: bytes) -> None:
        dados = extrair_damdfe(xml_mdfe)
        assert len(dados.chaves_cte) == 1
        assert len(dados.chaves_cte[0]) == 44
        assert dados.quantidade_cte == "1"
        assert dados.valor_carga == "10.000,00"
        assert dados.unidade_carga == "KG"
        assert dados.quantidade_carga == "15000.0000"

    def test_multiplos_ctes_preservam_ordem(self) -> None:
        chaves = ("3" * 44, "4" * 44)
        dados = extrair_damdfe(mdfe(chaves_cte=chaves))
        assert dados.chaves_cte == list(chaves)

    def test_campo_ausente_registrado(self) -> None:
        from tests.construir import sem_campo

        xml = sem_campo(mdfe(), "MDFe/infMDFe/ide/UFIni")
        dados = extrair_damdfe(xml)
        assert "uf_inicio" in dados.ausentes


class TestPdf:
    def test_paisagem(self, xml_mdfe: bytes) -> None:
        pdf = gerar_damdfe(extrair_damdfe(xml_mdfe))
        assert pdf.startswith(b"%PDF")
        pagina = PdfReader(BytesIO(pdf)).pages[0]
        assert float(pagina.mediabox.width) > float(pagina.mediabox.height)

    def test_conteudo(self, xml_mdfe: bytes) -> None:
        corpo = texto(gerar_damdfe(extrair_damdfe(xml_mdfe)))
        assert "DAMDFE" in corpo
        assert "Transportadora Exemplo LTDA" in corpo
        assert "PERCURSO" in corpo
        assert "MODAL RODOVIÁRIO" in corpo
        assert "ABC1D23" in corpo
        assert "10.000,00" in corpo

    def test_declara_grau_de_confianca_do_leiaute(self, xml_mdfe: bytes) -> None:
        # Este é o único documento cujo leiaute não tem XSD na base de referência.
        corpo = texto(gerar_damdfe(extrair_damdfe(xml_mdfe)))
        assert "A VALIDAR" in corpo
        assert "XSD" in corpo

    def test_avisa_campo_ausente(self) -> None:
        from tests.construir import sem_campo

        xml = sem_campo(mdfe(), "MDFe/infMDFe/ide/UFIni")
        corpo = texto(gerar_damdfe(extrair_damdfe(xml)))
        assert "Campos não encontrados" in corpo


class TestRegistro:
    def test_registrado(self) -> None:
        formatos = {(t.documento, t.formato) for t in disponiveis()}
        assert ("mdfe", "damdfe") in formatos

    def test_todos_os_documentos_tem_representacao(self) -> None:
        documentos = {t.documento for t in disponiveis()}
        assert {"nfe", "nfce", "nfse", "cte", "mdfe"} <= documentos

    def test_dispatch(self, xml_mdfe: bytes) -> None:
        assert gerar("mdfe", xml_mdfe, formato="damdfe").startswith(b"%PDF")


class TestRota:
    async def test_damdfe_pela_api(self, cliente, xml_mdfe: bytes) -> None:
        criado = await cliente.post(
            "/v1/tenants", json={"slug": "mdfe-tenant", "nome": "MDF-e LTDA"}
        )
        cabecalho = {"X-API-Key": criado.json()["api_key"]}
        resposta = await cliente.post(
            "/v1/representacoes?formato=damdfe",
            files={"arquivo": ("mdfe.xml", xml_mdfe, "application/xml")},
            headers=cabecalho,
        )
        assert resposta.status_code == 200, resposta.text
        assert "DAMDFE" in texto(resposta.content)
