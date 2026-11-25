"""Testes do DANFSe: extração do XML e fidelidade XML → PDF.

O teste de fidelidade extrai o texto do PDF gerado (`pypdf`) e confere que os
valores do XML aparecem no documento. Isso pega o defeito mais provável de um
renderizador fiscal: campo que existe no XML e não sai no PDF.

A fixture foi **construída à mão** a partir do leiaute 1.01 e do modelo de campos
da NT 008 — não é nota real. Os caminhos de extração seguem marcados [A VALIDAR]
em `docs/REFERENCIAS.md`.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from app.danfse.parser import parse_danfse
from app.danfse.render import gerar_danfse
from pypdf import PdfReader

from notasbr.erros import XmlInvalido

CHAVE = "35503081234567890123456789012345678901234567890123"
CNPJ_PRESTADOR = "11222333000181"
NOME_PRESTADOR = "BARBEARIA CENTRO LTDA"
NOME_TOMADOR = "CLIENTE EXEMPLO DA SILVA"

NFSE_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">
  <infNFSe Id="NFS{CHAVE}">
    <nNFSe>152</nNFSe>
    <cStat>100</cStat>
    <dhProc>2026-11-25T13:12:43-03:00</dhProc>
    <ambGer>2</ambGer>
    <finNFSe>0</finNFSe>
    <emit>
      <CNPJ>{CNPJ_PRESTADOR}</CNPJ>
      <xNome>{NOME_PRESTADOR}</xNome>
      <IM>123456</IM>
      <fone>1133334444</fone>
      <email>contato@barbearia.test</email>
      <end>
        <endNac><CEP>01001000</CEP></endNac>
        <xLgr>Rua da Barbearia</xLgr>
        <nro>100</nro>
        <xBairro>Centro</xBairro>
      </end>
    </emit>
    <DPS>
      <infDPS>
        <serie>1</serie>
        <nDPS>42</nDPS>
        <dCompet>2026-11-25</dCompet>
        <dhEmi>2026-11-25T13:12:40-03:00</dhEmi>
        <toma>
          <CPF>11144477735</CPF>
          <xNome>{NOME_TOMADOR}</xNome>
          <email>cliente@exemplo.test</email>
          <end>
            <endNac><CEP>04180112</CEP></endNac>
            <xLgr>Travessa 19 de Agosto</xLgr>
            <nro>123</nro>
            <xBairro>Jardim Maria Estela</xBairro>
          </end>
        </toma>
        <serv>
          <locPrest><cLocPrestacao>3550308</cLocPrestacao></locPrest>
          <cServ>
            <cTribNac>010701</cTribNac>
            <cNBS>123456789</cNBS>
            <xDescServ>Corte de cabelo masculino</xDescServ>
          </cServ>
        </serv>
        <valores>
          <vServPrest><vServ>85.00</vServ></vServPrest>
          <trib>
            <tribMun>
              <tribISSQN>1</tribISSQN>
              <tpRetISSQN>1</tpRetISSQN>
              <pAliq>0.0500</pAliq>
            </tribMun>
            <tribFed><vRetIRRF>1.28</vRetIRRF></tribFed>
          </trib>
        </valores>
      </infDPS>
    </DPS>
    <valores>
      <vLiq>83.72</vLiq>
    </valores>
    <IBSCBS>
      <valores>
        <trib>
          <gIBSCBS>
            <CST>000</CST>
            <cClassTrib>000001</cClassTrib>
            <vBC>85.00</vBC>
            <vIBSTot>0.09</vIBSTot>
            <gIBSUF><vIBSUF>0.04</vIBSUF></gIBSUF>
            <gIBSMun><vIBSMun>0.05</vIBSMun></gIBSMun>
            <gCBS><vCBS>0.77</vCBS></gCBS>
          </gIBSCBS>
        </trib>
        <vTotIBSCBS>0.86</vTotIBSCBS>
      </valores>
    </IBSCBS>
  </infNFSe>
</NFSe>
"""


class TestParser:
    def test_chave_sem_prefixo(self) -> None:
        dados = parse_danfse(NFSE_XML)
        assert dados.chave_acesso == CHAVE
        assert len(dados.chave_acesso) == 50

    def test_identificacao(self) -> None:
        dados = parse_danfse(NFSE_XML)
        assert dados.numero == "152"
        assert dados.numero_dps == "42"
        assert dados.serie_dps == "1"
        assert dados.competencia == "2026-11-25"
        assert dados.situacao == "100"
        assert dados.ambiente == "2"

    def test_prestador(self) -> None:
        dados = parse_danfse(NFSE_XML)
        assert dados.prestador.documento == CNPJ_PRESTADOR
        assert dados.prestador.nome == NOME_PRESTADOR
        assert dados.prestador.inscricao_municipal == "123456"
        assert dados.prestador.telefone == "1133334444"
        assert "Rua da Barbearia" in dados.prestador.endereco
        assert "Centro" in dados.prestador.endereco

    def test_tomador(self) -> None:
        dados = parse_danfse(NFSE_XML)
        assert dados.tomador is not None
        assert dados.tomador.documento == "11144477735"
        assert dados.tomador.nome == NOME_TOMADOR
        assert "Travessa 19 de Agosto" in dados.tomador.endereco

    def test_servico(self) -> None:
        dados = parse_danfse(NFSE_XML)
        assert dados.codigo_tributacao == "010701"
        assert dados.codigo_nbs == "123456789"
        assert dados.descricao_servico == "Corte de cabelo masculino"
        assert dados.local_prestacao == "3550308"

    def test_tributacao_municipal(self) -> None:
        dados = parse_danfse(NFSE_XML)
        assert dados.issqn.trib_issqn == "1"
        assert dados.issqn.retencao == "1"
        assert dados.issqn.aliquota == "0.0500"
        assert dados.issqn.nao_sujeito is False

    def test_tributacao_federal(self) -> None:
        dados = parse_danfse(NFSE_XML)
        assert dados.federal.ret_irrf == "1,28"

    def test_ibscbs_extraido(self) -> None:
        dados = parse_danfse(NFSE_XML)
        assert dados.tem_ibscbs() is True
        assert "000" in dados.ibscbs.cst_class
        assert "000001" in dados.ibscbs.cst_class
        assert dados.ibscbs.base_calculo == "85,00"
        assert dados.ibscbs.valor_ibs_uf == "0,04"
        assert dados.ibscbs.valor_ibs_mun == "0,05"
        assert dados.ibscbs.valor_cbs == "0,77"
        assert dados.ibscbs.total_ibs_cbs == "0,86"

    def test_totais(self) -> None:
        dados = parse_danfse(NFSE_XML)
        assert dados.totais.valor_servico == "85,00"
        assert dados.totais.valor_liquido == "83,72"

    def test_versao_do_layout(self) -> None:
        assert parse_danfse(NFSE_XML).versao_layout == "1.01"

    def test_nota_sem_ibscbs(self) -> None:
        sem = NFSE_XML.replace("<IBSCBS>", "<IGNORADO>").replace("</IBSCBS>", "</IGNORADO>")
        dados = parse_danfse(sem)
        assert dados.tem_ibscbs() is False

    def test_campos_ausentes_sao_registrados(self) -> None:
        minimo = (
            '<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">'
            '<infNFSe Id="NFS123"><nNFSe>1</nNFSe></infNFSe></NFSe>'
        )
        dados = parse_danfse(minimo)
        assert "prestador_nome" in dados.ausentes or "servico_descricao" in dados.ausentes

    def test_xml_invalido(self) -> None:
        with pytest.raises(XmlInvalido):
            parse_danfse(b"<NFSe><infNFSe>")


class TestPDF:
    @pytest.fixture(scope="class")
    def pdf(self) -> bytes:
        return gerar_danfse(parse_danfse(NFSE_XML))

    @pytest.fixture(scope="class")
    def texto(self, pdf: bytes) -> str:
        leitor = PdfReader(BytesIO(pdf))
        return "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)

    def test_e_pdf_valido(self, pdf: bytes) -> None:
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 3000

    def test_uma_pagina(self, pdf: bytes) -> None:
        assert len(PdfReader(BytesIO(pdf)).pages) == 1

    def test_titulo_do_documento(self, texto: str) -> None:
        assert "DANFSe" in texto

    def test_prestador_aparece(self, texto: str) -> None:
        assert NOME_PRESTADOR in texto
        assert CNPJ_PRESTADOR in texto

    def test_tomador_aparece(self, texto: str) -> None:
        assert NOME_TOMADOR in texto

    def test_numero_e_competencia(self, texto: str) -> None:
        assert "152" in texto
        assert "2026-11-25" in texto

    def test_servico_aparece(self, texto: str) -> None:
        assert "Corte de cabelo masculino" in texto
        assert "010701" in texto

    def test_secao_ibscbs_renderizada(self, texto: str) -> None:
        assert "IBS" in texto
        assert "CBS" in texto
        assert "0,77" in texto, "valor de CBS do XML deve aparecer no PDF"
        assert "0,86" in texto, "total IBS+CBS do XML deve aparecer no PDF"

    def test_valores_no_formato_brasileiro(self, texto: str) -> None:
        assert "85,00" in texto
        assert "83,72" in texto

    def test_chave_no_documento(self, texto: str) -> None:
        # A chave sai agrupada em blocos de 4; comparar sem espaços.
        assert CHAVE[:16] in texto.replace(" ", "")

    def test_rodape_declara_prevalencia_do_xml(self, texto: str) -> None:
        assert "XML autorizado prevalece" in texto.replace("\n", " ")

    def test_nota_sem_ibscbs_imprime_secao_com_ressalva(self) -> None:
        sem = NFSE_XML.replace("<IBSCBS>", "<IGNORADO>").replace("</IBSCBS>", "</IGNORADO>")
        pdf = gerar_danfse(parse_danfse(sem))
        texto = "\n".join(pagina.extract_text() or "" for pagina in PdfReader(BytesIO(pdf)).pages)
        assert "NÃO INFORMADO" in texto

    def test_campos_ausentes_viram_aviso_no_rodape(self) -> None:
        minimo = (
            '<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">'
            '<infNFSe Id="NFS123"><nNFSe>1</nNFSe></infNFSe></NFSe>'
        )
        pdf = gerar_danfse(parse_danfse(minimo))
        texto = "\n".join(pagina.extract_text() or "" for pagina in PdfReader(BytesIO(pdf)).pages)
        assert "Campos não encontrados" in texto
