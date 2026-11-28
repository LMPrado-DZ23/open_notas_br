"""Testes dos ramos de documento incompleto e de valor inválido dos DANFEs.

Os testes de `test_danfe.py`, `test_danfe_a4_etiquetas.py`, `test_cupom_dacte.py`
e `test_damdfe.py` cobrem o caminho feliz de cada representação impressa. Aqui o
alvo é o que sobra: campo ausente, valor não numérico, data fora do ISO,
documento que não é CNPJ nem CPF, `qVol` não numérico e os blocos opcionais do
PDF (dados adicionais, aviso de campos ausentes, continuação de itens).

Regra do produto que estes testes fixam: **campo que não está no XML sai vazio e
é listado como ausente — o gerador nunca inventa valor**. Por isso as asserções
são sobre o valor extraído e sobre o que aparece (ou não) no PDF, não sobre
"não levantou exceção".

Tudo é gerado localmente: nenhuma chamada de rede, nenhum documento real.
"""

from __future__ import annotations

import copy
from io import BytesIO
from xml.etree import ElementTree as ET

from app.danfe.a4 import extrair_danfe_a4, gerar_danfe_a4
from app.danfe.cte import extrair_dacte, gerar_dacte
from app.danfe.etiquetas import _quebrar, extrair_etiquetas, gerar_etiquetas
from app.danfe.mdfe import extrair_damdfe, gerar_damdfe
from app.danfe.nfce import extrair_cupom, gerar_cupom
from app.danfe.nfe import extrair_nfe, gerar_danfe_simplificado
from pypdf import PdfReader

from notasbr.xml_util import filhos, navegar
from tests.construir import com_campo, cte, mdfe, nfe, sem_campo, transformar


def texto_do_pdf(pdf: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages)


def _anexar(dados: bytes, caminho: str, tag: str, valor: str | None = None) -> bytes:
    """Acrescenta um elemento sob `caminho`, herdando o namespace do pai."""

    def acao(raiz: ET.Element) -> None:
        pai = navegar(raiz, caminho)
        assert pai is not None, f"caminho inexistente no fixture: {caminho}"
        prefixo = pai.tag[: pai.tag.index("}") + 1] if pai.tag.startswith("{") else ""
        novo = ET.SubElement(pai, f"{prefixo}{tag}")
        if valor is not None:
            novo.text = valor

    return transformar(dados, acao)


def _clonar_itens(dados: bytes, total: int) -> bytes:
    """Repete o primeiro `det` até o documento ter `total` itens."""

    def acao(raiz: ET.Element) -> None:
        inf = navegar(raiz, "NFe/infNFe")
        assert inf is not None
        existentes = filhos(inf, "det")
        for indice in range(len(existentes) + 1, total + 1):
            copia = copy.deepcopy(existentes[0])
            copia.set("nItem", str(indice))
            inf.append(copia)

    return transformar(dados, acao)


# ----------------------------------------------------------------------
# NF-e — DANFE Simplificado
# ----------------------------------------------------------------------
class TestNfeDocumentoForaDoPadrao:
    def test_cpf_do_destinatario_recebe_mascara_de_cpf(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/dest/CNPJ", "11144477735")
        assert extrair_nfe(xml).destinatario_documento == "111.444.777-35"

    def test_documento_de_tamanho_invalido_sai_como_veio(self) -> None:
        # 3 dígitos não são CNPJ (14) nem CPF (11): o DANFE imprime o valor cru
        # em vez de inventar pontuação — e NÃO registra isso em `ausentes`.
        xml = com_campo(nfe(), "NFe/infNFe/emit/CNPJ", "123")
        dados = extrair_nfe(xml)
        assert dados.emitente_cnpj == "123"
        assert "emitente_nome" not in dados.ausentes

    def test_data_fora_do_iso_sai_como_veio(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/ide/dhEmi", "15/01/2025")
        assert extrair_nfe(xml).emissao == "15/01/2025"

    def test_valor_nao_numerico_sai_como_veio_no_pdf(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/total/ICMSTot/vNF", "abc")
        dados = extrair_nfe(xml)
        assert dados.valor_total == "abc"
        corpo = texto_do_pdf(gerar_danfe_simplificado(dados))
        assert "R$ abc" in corpo


# ----------------------------------------------------------------------
# NFC-e — cupom em bobina
# ----------------------------------------------------------------------
class TestNfceRamos:
    def test_total_de_produtos_ausente_nao_e_inventado(self) -> None:
        xml = sem_campo(nfe(modelo="65"), "NFe/infNFe/total/ICMSTot/vProd")
        dados = extrair_cupom(xml)
        assert dados.valor_produtos == ""
        assert "valor_produtos" not in dados.ausentes  # não é obrigatório no cupom
        assert gerar_cupom(dados).startswith(b"%PDF")

    def test_total_de_produtos_nao_numerico_sai_como_veio(self) -> None:
        xml = com_campo(nfe(modelo="65"), "NFe/infNFe/total/ICMSTot/vProd", "abc")
        assert extrair_cupom(xml).valor_produtos == "abc"

    def test_data_fora_do_iso_sai_como_veio(self) -> None:
        xml = com_campo(nfe(modelo="65"), "NFe/infNFe/ide/dhEmi", "ontem")
        assert extrair_cupom(xml).emissao == "ontem"

    def test_cpf_do_emitente_recebe_mascara_de_cpf(self) -> None:
        xml = com_campo(nfe(modelo="65"), "NFe/infNFe/emit/CNPJ", "11144477735")
        assert extrair_cupom(xml).emitente_documento == "111.444.777-35"

    def test_documento_de_tamanho_invalido_sai_como_veio(self) -> None:
        xml = com_campo(nfe(modelo="65"), "NFe/infNFe/emit/CNPJ", "123")
        assert extrair_cupom(xml).emitente_documento == "123"

    def test_desconto_aparece_quando_diferente_de_zero(self) -> None:
        xml = com_campo(
            nfe(modelo="65", valor_item="38.90"), "NFe/infNFe/total/ICMSTot/vDesc", "10.00"
        )
        dados = extrair_cupom(xml)
        assert dados.valor_desconto == "10,00"
        corpo = texto_do_pdf(gerar_cupom(dados))
        assert "DESCONTO" in corpo
        assert "10,00" in corpo

    def test_desconto_zerado_nao_ocupa_linha_no_cupom(self) -> None:
        dados = extrair_cupom(nfe(modelo="65", valor_item="38.90"))
        assert dados.valor_desconto == "0,00"
        assert "DESCONTO" not in texto_do_pdf(gerar_cupom(dados))

    def test_informacoes_adicionais_entram_no_cupom(self) -> None:
        xml = _anexar(nfe(modelo="65"), "NFe/infNFe", "infAdic")
        xml = _anexar(xml, "NFe/infNFe/infAdic", "infCpl", "Pedido 1234 do cliente")
        dados = extrair_cupom(xml)
        assert dados.informacoes_adicionais == "Pedido 1234 do cliente"
        assert "Pedido 1234 do cliente" in texto_do_pdf(gerar_cupom(dados))

    def test_campos_ausentes_ficam_listados_no_cupom(self) -> None:
        xml = sem_campo(nfe(modelo="65"), "NFe/infNFe/emit/xNome")
        dados = extrair_cupom(xml)
        assert dados.ausentes == ["emitente_nome"]
        corpo = texto_do_pdf(gerar_cupom(dados))
        assert "Campos ausentes no XML" in corpo
        assert "emitente_nome" in corpo

    def test_qr_code_fora_do_suplemento_padrao_e_encontrado(self) -> None:
        # Há emissores que serializam o `qrCode` fora de `infNFeSupl`. O cupom
        # varre o documento e usa o que existir; URL inventada seria pior.
        url = "https://nfce.exemplo/qr?p=1"
        xml = _anexar(nfe(modelo="65"), "NFe", "qrCode", url)
        dados = extrair_cupom(xml)
        assert dados.qr_code == url
        pdf = gerar_cupom(dados)
        assert b"/Image" in pdf, "QR Code precisa entrar como imagem no PDF"
        assert "QR Code não presente" not in texto_do_pdf(pdf)


# ----------------------------------------------------------------------
# Etiquetas de volume
# ----------------------------------------------------------------------
class TestEtiquetasRamos:
    def test_cep_fora_do_padrao_sai_como_veio(self) -> None:
        xml = com_campo(
            nfe(volumes=[{"qVol": "1", "esp": "CAIXA"}]),
            "NFe/infNFe/dest/enderDest/CEP",
            "0100-000",
        )
        dados = extrair_etiquetas(xml)
        assert dados.destinatario_cep == "0100-000"
        assert "CEP 0100-000" in texto_do_pdf(gerar_etiquetas(dados))

    def test_coleta_fora_do_iso_sai_como_veio(self) -> None:
        xml = com_campo(nfe(volumes=[{"qVol": "1"}]), "NFe/infNFe/ide/dhEmi", "ontem")
        dados = extrair_etiquetas(xml)
        assert dados.coleta == "ontem"
        assert "ontem" in texto_do_pdf(gerar_etiquetas(dados))

    def test_peso_nao_numerico_sai_como_veio(self) -> None:
        xml = nfe(volumes=[{"qVol": "1", "pesoB": "abc"}])
        dados = extrair_etiquetas(xml)
        assert dados.volumes[0].peso_bruto == "abc"
        assert "abc" in texto_do_pdf(gerar_etiquetas(dados))

    def test_qvol_nao_numerico_vira_um_volume(self) -> None:
        # `qVol` é a quantidade do grupo; quando não é número, o volume informado
        # continua sendo um volume — descartar o grupo inteiro sumiria com a caixa.
        dados = extrair_etiquetas(nfe(volumes=[{"qVol": "duas", "esp": "CAIXA"}]))
        assert len(dados.volumes) == 1
        assert dados.volumes[0].quantidade == "duas"
        assert dados.volumes[0].total == 1

    def test_endereco_longo_quebra_sem_perder_palavra(self) -> None:
        endereco = (
            "Avenida Doutor Antônio de Albuquerque e Silva Nascimento, 1500, Bloco B, "
            "Jardim das Acácias, São Paulo, SP"
        )
        linhas = _quebrar(endereco, 78)
        assert len(linhas) > 1
        assert all(len(linha) <= 78 for linha in linhas)
        assert " ".join(linhas) == endereco


# ----------------------------------------------------------------------
# NF-e — DANFE A4
# ----------------------------------------------------------------------
class TestDanfeA4Ramos:
    def test_total_ausente_nao_e_inventado(self) -> None:
        xml = sem_campo(nfe(), "NFe/infNFe/total/ICMSTot/vOutro")
        dados = extrair_danfe_a4(xml)
        assert dados.valor_outras == ""
        corpo = texto_do_pdf(gerar_danfe_a4(dados))
        assert "OUTRAS DESPESAS" not in corpo, "campo vazio não pode ocupar linha no bloco"

    def test_total_nao_numerico_sai_como_veio(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/total/ICMSTot/vBC", "abc")
        dados = extrair_danfe_a4(xml)
        assert dados.base_icms == "abc"
        assert "BASE ICMS" in texto_do_pdf(gerar_danfe_a4(dados))

    def test_cpf_do_emitente_recebe_mascara_de_cpf(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/emit/CNPJ", "11144477735")
        assert extrair_danfe_a4(xml).emitente_documento == "111.444.777-35"

    def test_documento_de_tamanho_invalido_sai_como_veio(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/emit/CNPJ", "123")
        assert extrair_danfe_a4(xml).emitente_documento == "123"

    def test_muitos_itens_avisam_continuacao(self) -> None:
        # O DANFE A4 imprime 14 itens por folha; o excedente não pode sumir calado.
        dados = extrair_danfe_a4(_clonar_itens(nfe(), 15))
        assert len(dados.itens) == 15
        corpo = texto_do_pdf(gerar_danfe_a4(dados))
        assert "mais 1 item(ns)" in corpo

    def test_dados_adicionais_entram_no_danfe(self) -> None:
        xml = _anexar(nfe(), "NFe/infNFe", "infAdic")
        xml = _anexar(xml, "NFe/infNFe/infAdic", "infCpl", "Pedido 1234 do cliente")
        dados = extrair_danfe_a4(xml)
        assert dados.informacoes_adicionais == "Pedido 1234 do cliente"
        corpo = texto_do_pdf(gerar_danfe_a4(dados))
        assert "DADOS ADICIONAIS" in corpo
        assert "Pedido 1234 do cliente" in corpo


# ----------------------------------------------------------------------
# CT-e — DACTE
# ----------------------------------------------------------------------
class TestDacteRamos:
    def test_campo_vazio_e_omitido_do_bloco(self) -> None:
        dados = extrair_dacte(sem_campo(cte(), "CTe/infCte/ide/natOp"))
        assert dados.natureza == ""
        corpo = texto_do_pdf(gerar_dacte(dados))
        assert "NATUREZA DA OPERAÇÃO" not in corpo
        assert "PRESTAÇÃO DO SERVIÇO" in corpo

    def test_campos_ausentes_ficam_no_rodape(self) -> None:
        dados = extrair_dacte(sem_campo(cte(), "CTe/infCte/emit/xNome"))
        assert dados.ausentes == ["emitente_nome"]
        corpo = texto_do_pdf(gerar_dacte(dados))
        assert "Campos não encontrados" in corpo
        assert "emitente_nome" in corpo

    def test_valor_a_receber_ausente_nao_e_inventado(self) -> None:
        dados = extrair_dacte(sem_campo(cte(), "CTe/infCte/vPrest/vRec"))
        assert dados.valor_receber == ""
        assert "valor_receber" not in dados.ausentes  # não é obrigatório no DACTE

    def test_valor_nao_numerico_sai_como_veio(self) -> None:
        xml = com_campo(cte(), "CTe/infCte/imp/ICMS/ICMS00/vBC", "n/d")
        assert extrair_dacte(xml).base_icms == "n/d"

    def test_cpf_do_remetente_recebe_mascara_de_cpf(self) -> None:
        xml = com_campo(cte(), "CTe/infCte/rem/CNPJ", "11144477735")
        assert extrair_dacte(xml).remetente_documento == "111.444.777-35"

    def test_documento_de_tamanho_invalido_sai_como_veio(self) -> None:
        xml = com_campo(cte(), "CTe/infCte/rem/CNPJ", "123")
        assert extrair_dacte(xml).remetente_documento == "123"

    def test_data_fora_do_iso_sai_como_veio(self) -> None:
        xml = com_campo(cte(), "CTe/infCte/ide/dhEmi", "20/01/2025")
        assert extrair_dacte(xml).emissao == "20/01/2025"


# ----------------------------------------------------------------------
# MDF-e — DAMDFE
# ----------------------------------------------------------------------
class TestDamdfeRamos:
    def test_valor_da_carga_ausente_e_registrado(self) -> None:
        dados = extrair_damdfe(sem_campo(mdfe(), "MDFe/infMDFe/tot/vCarga"))
        assert dados.valor_carga == ""
        assert "valor_carga" in dados.ausentes
        corpo = texto_do_pdf(gerar_damdfe(dados))
        assert "VALOR DA CARGA" not in corpo

    def test_valor_da_carga_nao_numerico_sai_como_veio(self) -> None:
        xml = com_campo(mdfe(), "MDFe/infMDFe/tot/vCarga", "n/d")
        dados = extrair_damdfe(xml)
        assert dados.valor_carga == "n/d"
        assert "n/d" in texto_do_pdf(gerar_damdfe(dados))

    def test_emitente_cpf_recebe_mascara_de_cpf(self) -> None:
        xml = sem_campo(mdfe(), "MDFe/infMDFe/emit/CNPJ")
        xml = _anexar(xml, "MDFe/infMDFe/emit", "CPF", "11144477735")
        assert extrair_damdfe(xml).emitente_documento == "111.444.777-35"

    def test_documento_de_tamanho_invalido_sai_como_veio(self) -> None:
        xml = com_campo(mdfe(), "MDFe/infMDFe/emit/CNPJ", "123")
        assert extrair_damdfe(xml).emitente_documento == "123"

    def test_data_fora_do_iso_sai_como_veio(self) -> None:
        xml = com_campo(mdfe(), "MDFe/infMDFe/ide/dhEmi", "sem-data")
        assert extrair_damdfe(xml).emissao == "sem-data"

    def test_informacoes_complementares_entram_no_damdfe(self) -> None:
        xml = _anexar(mdfe(), "MDFe/infMDFe", "infAdic")
        xml = _anexar(xml, "MDFe/infMDFe/infAdic", "infCpl", "Pedido 1234 do cliente")
        dados = extrair_damdfe(xml)
        assert dados.informacoes_adicionais == "Pedido 1234 do cliente"
        corpo = texto_do_pdf(gerar_damdfe(dados))
        assert "INFORMAÇÕES COMPLEMENTARES" in corpo
        assert "Pedido 1234 do cliente" in corpo
