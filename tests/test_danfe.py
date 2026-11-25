"""Testes do adapter de representação impressa e do DANFE Simplificado.

A NF-e vem do construtor de fixture já usado pela auditoria (`tests/construir.nfe`),
que gera XML autoconsistente com chave válida. Assim o DANFE é testado contra
documento estruturalmente correto, não contra string escrita à mão.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from app.danfe import (
    RepresentacaoNaoImplementada,
    TipoRepresentacao,
    disponiveis,
    gerar,
    obter,
)
from app.danfe.nfe import DanfeSimplificado, Danfse, extrair_nfe, gerar_danfe_simplificado
from pypdf import PdfReader

from tests.construir import nfe


def texto_do_pdf(pdf: bytes) -> str:
    return "\n".join(pagina.extract_text() or "" for pagina in PdfReader(BytesIO(pdf)).pages)


class TestRegistro:
    def test_representacoes_disponiveis(self) -> None:
        tipos = {(t.documento, t.formato) for t in disponiveis()}
        assert ("nfe", "danfe_simplificado") in tipos
        assert ("nfse", "danfse") in tipos

    def test_obter_retorna_implementacao(self) -> None:
        representacao = obter("nfe", "danfe_simplificado")
        assert isinstance(representacao, DanfeSimplificado)

    def test_representacao_inexistente_falha_alto(self) -> None:
        # Formato que nunca vai existir: o caminho de erro precisa listar o que
        # existe, nunca devolver PDF incompleto. Testar contra um formato do
        # roadmap quebraria o teste a cada fase concluída.
        with pytest.raises(RepresentacaoNaoImplementada, match="danfe"):
            obter("nfe", "formato_que_nao_existe")

    def test_documento_sem_representacao(self) -> None:
        with pytest.raises(RepresentacaoNaoImplementada, match="não existe"):
            obter("nfce", "dacte")

    def test_tipo_e_imutavel(self) -> None:
        tipo = TipoRepresentacao(documento="nfe", formato="danfe_simplificado")
        assert hash(tipo) == hash(TipoRepresentacao("nfe", "danfe_simplificado"))


@pytest.fixture(scope="module")
def xml() -> bytes:
    """NF-e sintética autoconsistente, reaproveitada pelos casos de DANFE."""
    return nfe()


@pytest.fixture(scope="module")
def pdf(xml: bytes) -> bytes:
    return gerar_danfe_simplificado(extrair_nfe(xml))


class TestExtracaoNfe:
    def test_chave_extraida_sem_prefixo(self, xml: bytes) -> None:
        dados = extrair_nfe(xml)
        assert len(dados.chave) == 44
        assert dados.chave.isdigit()

    def test_emitente(self, xml: bytes) -> None:
        dados = extrair_nfe(xml)
        assert dados.emitente_nome == "Empresa Exemplo LTDA"
        assert dados.emitente_cnpj == "11.222.333/0001-81"
        assert dados.emitente_uf == "SP"

    def test_destinatario(self, xml: bytes) -> None:
        dados = extrair_nfe(xml)
        assert dados.destinatario_nome == "Cliente Exemplo SA"
        assert dados.destinatario_uf == "SP"
        assert "Rua Exemplo" in dados.destinatario_endereco

    def test_identificacao(self, xml: bytes) -> None:
        dados = extrair_nfe(xml)
        assert dados.numero == "123"
        assert dados.serie == "1"
        assert dados.emissao == "15/01/2025"
        assert dados.operacao == "1-SAÍDA"

    def test_valor_formatado(self, xml: bytes) -> None:
        dados = extrair_nfe(xml)
        assert dados.valor_total == "1.000,00"

    def test_protocolo(self, xml: bytes) -> None:
        dados = extrair_nfe(xml)
        assert dados.protocolo == "135250000000001"

    def test_sem_ausentes_no_fixture_completo(self, xml: bytes) -> None:
        assert extrair_nfe(xml).ausentes == []

    def test_operacao_de_entrada(self) -> None:
        from tests.construir import com_campo

        xml = com_campo(nfe(), "NFe/infNFe/ide/tpNF", "0")
        assert extrair_nfe(xml).operacao == "0-ENTRADA"


class TestPdf:
    def test_e_pdf_valido(self, pdf: bytes) -> None:
        assert pdf.startswith(b"%PDF")

    def test_uma_pagina(self, pdf: bytes) -> None:
        assert len(PdfReader(BytesIO(pdf)).pages) == 1

    def test_titulo(self, pdf: bytes) -> None:
        assert "DANFE SIMPLIFICADO" in texto_do_pdf(pdf)

    def test_emitente_no_documento(self, pdf: bytes) -> None:
        texto = texto_do_pdf(pdf)
        assert "Empresa Exemplo LTDA" in texto
        assert "11.222.333/0001-81" in texto
        assert "SP" in texto

    def test_destinatario_no_documento(self, pdf: bytes) -> None:
        texto = texto_do_pdf(pdf)
        assert "Cliente Exemplo SA" in texto
        assert "Rua Exemplo" in texto

    def test_identificacao_no_documento(self, pdf: bytes) -> None:
        texto = texto_do_pdf(pdf)
        assert "123" in texto
        assert "15/01/2025" in texto
        assert "1-SAÍDA" in texto

    def test_valor_no_documento(self, pdf: bytes) -> None:
        assert "1.000,00" in texto_do_pdf(pdf)

    def test_chave_no_documento(self, pdf: bytes, xml: bytes) -> None:
        chave = extrair_nfe(xml).chave
        assert chave[:16] in texto_do_pdf(pdf).replace(" ", "")

    def test_protocolo_no_documento(self, pdf: bytes) -> None:
        assert "135250000000001" in texto_do_pdf(pdf)

    def test_rodape_declara_ressalva_de_leiaute(self, pdf: bytes) -> None:
        assert "A VALIDAR" in texto_do_pdf(pdf)

    def test_campos_ausentes_viram_aviso(self) -> None:
        from tests.construir import sem_campo

        xml = sem_campo(nfe(), "NFe/infNFe/dest/xNome")
        dados = extrair_nfe(xml)
        assert "destinatario_nome" in dados.ausentes

        texto = texto_do_pdf(gerar_danfe_simplificado(dados))
        assert "Campos não encontrados" in texto


class TestDispatch:
    def test_gerar_por_documento_e_formato(self) -> None:
        pdf = gerar("nfe", nfe(), formato="danfe_simplificado")
        assert pdf.startswith(b"%PDF")

    def test_danfse_delegado(self, cliente) -> None:
        from tests.test_danfse import NFSE_XML

        pdf = Danfse().gerar(NFSE_XML.encode("utf-8"))
        assert pdf.startswith(b"%PDF")
        assert "DANFSe" in texto_do_pdf(pdf)
