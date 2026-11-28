"""Regras tributárias: CFOP, NCM, ICMS, CRT e PIS/COFINS.

Cada teste aplica **uma** mutação no fixture e verifica o código e a severidade. A distinção
erro x aviso importa: CFOP malformado é dado fiscal inválido (erro); NCM ausente no item é lacuna
que a norma admite em casos específicos (aviso).
"""

from __future__ import annotations

from notasbr import Severidade, auditar_bytes
from tests.construir import com_campo, sem_campo, transformar

NS = "http://www.portalfiscal.inf.br/nfe"


def _codigos(xml: bytes, severidade: Severidade | None = None) -> set[str]:
    relatorio = auditar_bytes(xml)
    achados = relatorio.achados if severidade is None else relatorio.por_severidade(severidade)
    return {a.codigo for a in achados}


class TestCfop:
    def test_cfop_com_tres_digitos_vira_erro(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/det/prod/CFOP", "510")

        assert "TRIB-CFOP-001" in _codigos(xml, Severidade.ERRO)

    def test_cfop_com_grupo_invalido_vira_erro(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/det/prod/CFOP", "9101")

        assert "TRIB-CFOP-001" in _codigos(xml, Severidade.ERRO)

    def test_cfop_com_letra_vira_erro(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/det/prod/CFOP", "5A01")

        assert "TRIB-CFOP-001" in _codigos(xml, Severidade.ERRO)

    def test_cfop_valido_nao_gera_achado(self, xml_nfe: bytes) -> None:
        assert "TRIB-CFOP-001" not in _codigos(xml_nfe)

    def test_tpnf_invalido_vira_aviso(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/ide/tpNF", "9")

        assert "TRIB-CFOP-002" in _codigos(xml, Severidade.AVISO)

    def test_cfop_de_entrada_com_operacao_de_saida_vira_erro(self, xml_nfe: bytes) -> None:
        """tpNF=1 (saída) com CFOP 1.xxx (entrada) é incoerência de escrituração."""
        xml = com_campo(xml_nfe, "NFe/infNFe/det/prod/CFOP", "1102")

        assert "TRIB-CFOP-002" in _codigos(xml, Severidade.ERRO)


class TestNcm:
    def test_ncm_ausente_vira_aviso(self, xml_nfe: bytes) -> None:
        xml = sem_campo(xml_nfe, "NFe/infNFe/det/prod/NCM")

        assert "TRIB-NCM-001" in _codigos(xml, Severidade.AVISO)

    def test_ncm_com_sete_digitos_vira_aviso(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/det/prod/NCM", "1234567")

        assert "TRIB-NCM-001" in _codigos(xml, Severidade.AVISO)

    def test_ncm_valido_nao_gera_achado(self, xml_nfe: bytes) -> None:
        assert "TRIB-NCM-001" not in _codigos(xml_nfe)


class TestIcms:
    def test_item_sem_grupo_de_icms_vira_erro(self, xml_nfe: bytes) -> None:
        def remover_grupo(raiz):
            for item in raiz.iter():
                if not item.tag.endswith("det"):
                    continue
                for filho in list(item):
                    if filho.tag.endswith("imposto"):
                        for neto in list(filho):
                            if neto.tag.endswith("ICMS"):
                                filho.remove(neto)

        xml = transformar(xml_nfe, remover_grupo)

        assert "TRIB-ICMS-001" in _codigos(xml, Severidade.ERRO)

    def test_grupo_sem_cst_nem_csosn_vira_erro(self, xml_nfe: bytes) -> None:
        def limpar_cst(raiz):
            for elemento in raiz.iter():
                if elemento.tag.endswith(("CST", "CSOSN")) and elemento.text:
                    elemento.text = ""

        xml = transformar(xml_nfe, limpar_cst)

        assert "TRIB-ICMS-001" in _codigos(xml, Severidade.ERRO)


class TestCrt:
    def test_crt_invalido_vira_erro(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/emit/CRT", "9")

        assert "TRIB-CRT-001" in _codigos(xml, Severidade.ERRO)

    def test_crt_ausente_e_pulado(self, xml_nfe: bytes) -> None:
        xml = sem_campo(xml_nfe, "NFe/infNFe/emit/CRT")
        relatorio = auditar_bytes(xml)

        assert "TRIB-CRT-001" in {p.codigo for p in relatorio.puladas}


class TestPisCofins:
    def test_item_sem_grupo_pis_vira_aviso(self, xml_nfe: bytes) -> None:
        def remover_pis(raiz):
            for elemento in list(raiz.iter()):
                if elemento.tag.endswith("PIS") and len(elemento):
                    pai = next(
                        (p for p in raiz.iter() if elemento in list(p)),
                        None,
                    )
                    if pai is not None:
                        pai.remove(elemento)

        xml = transformar(xml_nfe, remover_pis)

        assert "TRIB-PIS-COFINS-001" in _codigos(xml, Severidade.AVISO)

    def test_cst_fora_da_tabela_vira_erro(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/det/imposto/ICMS/ICMS00/CST", "99")

        assert "TRIB-ICMS-001" in _codigos(xml, Severidade.ERRO)

    def test_csosn_fora_da_tabela_vira_erro(self, xml_nfe: bytes) -> None:
        """Simples usa CSOSN; valor inexistente é erro de tabela."""

        def trocar_para_csosn(raiz):
            for elemento in raiz.iter():
                if elemento.tag.endswith("ICMS00"):
                    cst = next(e for e in elemento if e.tag.endswith("CST"))
                    cst.tag = "{http://www.portalfiscal.inf.br/nfe}CSOSN"
                    cst.text = "999"

        xml = transformar(xml_nfe, trocar_para_csosn)

        assert "TRIB-ICMS-001" in _codigos(xml, Severidade.ERRO)
