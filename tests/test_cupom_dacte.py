"""Testes do cupom NFC-e e do DACTE."""

from __future__ import annotations

from io import BytesIO

import pytest
from app.danfe import disponiveis, gerar
from app.danfe.cte import extrair_dacte, gerar_dacte
from app.danfe.nfce import extrair_cupom, gerar_cupom
from pypdf import PdfReader

from tests.construir import cte, nfe


def texto(pdf: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages)


@pytest.fixture(scope="module")
def xml_nfce() -> bytes:
    return nfe(modelo="65", valor_item="38.90")


@pytest.fixture(scope="module")
def xml_cte() -> bytes:
    return cte()


class TestCupomNfce:
    def test_extrai_identificacao(self, xml_nfce: bytes) -> None:
        dados = extrair_cupom(xml_nfce)
        assert dados.numero == "123"
        assert len(dados.chave) == 44
        assert dados.emitente_nome == "Empresa Exemplo LTDA"
        assert dados.emitente_documento == "11.222.333/0001-81"

    def test_extrai_itens(self, xml_nfce: bytes) -> None:
        dados = extrair_cupom(xml_nfce)
        assert len(dados.itens) == 1
        assert dados.itens[0].descricao
        assert dados.itens[0].valor_total

    def test_extrai_pagamento(self, xml_nfce: bytes) -> None:
        dados = extrair_cupom(xml_nfce)
        assert dados.forma_pagamento == "Dinheiro"
        assert dados.valor_total == "38,90"

    def test_sem_qr_code_no_xml(self, xml_nfce: bytes) -> None:
        dados = extrair_cupom(xml_nfce)
        # A fixture não traz infNFeSupl/qrCode: o cupom precisa avisar, não inventar.
        assert dados.qr_code == ""

    def test_pdf_valido_em_bobina(self, xml_nfce: bytes) -> None:
        pdf = gerar_cupom(extrair_cupom(xml_nfce))
        assert pdf.startswith(b"%PDF")
        pagina = PdfReader(BytesIO(pdf)).pages[0]
        # 80 mm de largura = ~227 pt, bem mais estreito que A4.
        assert float(pagina.mediabox.width) < 240
        assert float(pagina.mediabox.width) > 200

    def test_conteudo_do_cupom(self, xml_nfce: bytes) -> None:
        corpo = texto(gerar_cupom(extrair_cupom(xml_nfce)))
        assert "DANFE NFC-e" in corpo
        assert "Empresa Exemplo LTDA" in corpo
        assert "TOTAL" in corpo
        assert "38,90" in corpo
        assert "CHAVE DE ACESSO" in corpo

    def test_qr_ausente_gera_aviso(self, xml_nfce: bytes) -> None:
        corpo = texto(gerar_cupom(extrair_cupom(xml_nfce)))
        assert "QR Code não presente" in corpo

    def test_gera_qr_quando_xml_traz(self) -> None:
        from tests.construir import transformar

        def adicionar_suplemento(raiz):
            import xml.etree.ElementTree as ET

            # infNFeSupl é irmão de infNFe, ambos filhos de NFe.
            ns = "{http://www.portalfiscal.inf.br/nfe}"
            nfe_elem = raiz.find(f"{ns}NFe")
            supl = ET.SubElement(nfe_elem, f"{ns}infNFeSupl")
            ET.SubElement(
                supl, "{http://www.portalfiscal.inf.br/nfe}qrCode"
            ).text = "https://www.nfce.fazenda.sp.gov.br/qrcode?p=chave|csc|hash"

        xml = transformar(nfe(modelo="65"), adicionar_suplemento)
        dados = extrair_cupom(xml)
        assert dados.qr_code.startswith("https://")
        pdf = gerar_cupom(dados)
        assert pdf.startswith(b"%PDF")
        assert "QR Code não presente" not in texto(pdf)


class TestDacte:
    def test_extrai_cabecalho(self, xml_cte: bytes) -> None:
        dados = extrair_dacte(xml_cte)
        assert dados.numero == "456"
        assert dados.serie == "1"
        assert dados.modelo == "57"
        assert len(dados.chave) == 44
        assert dados.protocolo == "135250000000002"
        assert dados.modal == "01-Rodoviário"

    def test_extrai_partes(self, xml_cte: bytes) -> None:
        dados = extrair_dacte(xml_cte)
        assert dados.emitente_nome == "Transportadora Exemplo LTDA"
        assert dados.remetente_nome == "Remetente Exemplo"
        assert dados.destinatario_nome == "Destinatario Exemplo"
        # O grupo `toma` não existe na fixture: não pode ser deduzido.
        assert dados.tomador_nome == ""

    def test_extrai_valores(self, xml_cte: bytes) -> None:
        dados = extrair_dacte(xml_cte)
        assert dados.valor_servico == "1.500,00"
        assert dados.valor_icms == "180,00"
        assert dados.valor_carga == "10.000,00"

    def test_extrai_componentes_e_chaves(self, xml_cte: bytes) -> None:
        dados = extrair_dacte(xml_cte)
        assert ("Frete peso", "1.500,00") in dados.componentes
        assert len(dados.chaves_nfe) == 1
        assert len(dados.chaves_nfe[0]) == 44

    def test_pdf_paisagem(self, xml_cte: bytes) -> None:
        pdf = gerar_dacte(extrair_dacte(xml_cte))
        assert pdf.startswith(b"%PDF")
        pagina = PdfReader(BytesIO(pdf)).pages[0]
        assert float(pagina.mediabox.width) > float(pagina.mediabox.height)

    def test_conteudo_do_dacte(self, xml_cte: bytes) -> None:
        corpo = texto(gerar_dacte(extrair_dacte(xml_cte)))
        assert "DACTE" in corpo
        assert "Transportadora Exemplo LTDA" in corpo
        assert "Remetente Exemplo" in corpo
        assert "Destinatario Exemplo" in corpo
        assert "1.500,00" in corpo
        assert "PRESTAÇÃO DO SERVIÇO" in corpo
        assert "A VALIDAR" in corpo

    def test_tomador_nao_informado_aparece(self, xml_cte: bytes) -> None:
        corpo = texto(gerar_dacte(extrair_dacte(xml_cte)))
        assert "não informado" in corpo


class TestRegistro:
    def test_formatos_novos_registrados(self) -> None:
        formatos = {(t.documento, t.formato) for t in disponiveis()}
        assert ("nfce", "cupom") in formatos
        assert ("cte", "dacte") in formatos

    def test_dispatch_cupom(self, xml_nfce: bytes) -> None:
        assert gerar("nfce", xml_nfce, formato="cupom").startswith(b"%PDF")

    def test_dispatch_dacte(self, xml_cte: bytes) -> None:
        assert gerar("cte", xml_cte, formato="dacte").startswith(b"%PDF")


class TestRota:
    async def test_cupom_pela_api(self, cliente, xml_nfce: bytes) -> None:
        criado = await cliente.post(
            "/v1/tenants", json={"slug": "nfce-tenant", "nome": "NFC-e LTDA"}
        )
        cabecalho = {"X-API-Key": criado.json()["api_key"]}
        resposta = await cliente.post(
            "/v1/representacoes?formato=cupom",
            files={"arquivo": ("nfce.xml", xml_nfce, "application/xml")},
            headers=cabecalho,
        )
        assert resposta.status_code == 200, resposta.text
        assert "DANFE NFC-e" in texto(resposta.content)

    async def test_dacte_pela_api(self, cliente, xml_cte: bytes) -> None:
        criado = await cliente.post("/v1/tenants", json={"slug": "cte-tenant", "nome": "CT-e LTDA"})
        cabecalho = {"X-API-Key": criado.json()["api_key"]}
        resposta = await cliente.post(
            "/v1/representacoes?formato=dacte",
            files={"arquivo": ("cte.xml", xml_cte, "application/xml")},
            headers=cabecalho,
        )
        assert resposta.status_code == 200, resposta.text
        assert "DACTE" in texto(resposta.content)

    async def test_formato_inexistente_lista_os_reais(self, cliente) -> None:
        criado = await cliente.post("/v1/tenants", json={"slug": "fmt-tenant", "nome": "Fmt LTDA"})
        cabecalho = {"X-API-Key": criado.json()["api_key"]}
        resposta = await cliente.post(
            "/v1/representacoes?formato=mdfe",
            files={"arquivo": ("x.xml", nfe(), "application/xml")},
            headers=cabecalho,
        )
        assert resposta.status_code == 422
        assert "dacte" in str(resposta.json()["detail"])
