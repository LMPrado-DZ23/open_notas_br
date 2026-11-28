"""Regras de totalização: divergência de soma vira erro, ausência vira aviso ou pulo.

A regra usa tolerância de 1 centavo e distingue três situações: campo ausente (pular), item sem
valor (aviso, porque a soma pode não fechar por dado faltante) e soma divergente (erro). Trocar uma
pela outra muda o veredito do documento — por isso cada caso tem teste.
"""

from __future__ import annotations

from notasbr import Severidade, auditar_bytes
from tests.construir import com_campo, sem_campo


def _codigos(xml: bytes, severidade: Severidade | None = None) -> set[str]:
    relatorio = auditar_bytes(xml)
    achados = relatorio.achados if severidade is None else relatorio.por_severidade(severidade)
    return {a.codigo for a in achados}


class TestTotalProdutos:
    def test_soma_divergente_vira_erro(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/total/ICMSTot/vProd", "999.00")

        assert "TOTAL-VPROD-001" in _codigos(xml, Severidade.ERRO)

    def test_item_sem_vprod_vira_aviso(self, xml_nfe: bytes) -> None:
        xml = sem_campo(xml_nfe, "NFe/infNFe/det/prod/vProd")

        relatorio = auditar_bytes(xml)
        avisos = {a.codigo for a in relatorio.por_severidade(Severidade.AVISO)}

        assert "TOTAL-VPROD-001" in avisos
        # A soma fica menor que o total: aviso aponta o dado faltante e erro aponta a divergência.
        # Os dois são verdadeiros ao mesmo tempo — negar o erro era expectativa minha, não regra.

    def test_vprod_ausente_no_total_e_pulado(self, xml_nfe: bytes) -> None:
        xml = sem_campo(xml_nfe, "NFe/infNFe/total/ICMSTot/vProd")
        relatorio = auditar_bytes(xml)

        assert "TOTAL-VPROD-001" in {p.codigo for p in relatorio.puladas}

    def test_soma_correta_nao_gera_achado(self, xml_nfe: bytes) -> None:
        assert "TOTAL-VPROD-001" not in _codigos(xml_nfe)


class TestValorTotal:
    def test_vnf_zero_vira_erro(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/total/ICMSTot/vNF", "0.00")

        assert "TOTAL-VNF-001" in _codigos(xml, Severidade.ERRO)

    def test_vnf_negativo_vira_erro(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/total/ICMSTot/vNF", "-1.00")

        assert "TOTAL-VNF-001" in _codigos(xml, Severidade.ERRO)

    def test_vnf_ausente_nao_avalia(self, xml_nfe: bytes) -> None:
        xml = sem_campo(xml_nfe, "NFe/infNFe/total/ICMSTot/vNF")

        assert "TOTAL-VNF-001" not in _codigos(xml)


class TestPagamentos:
    def test_pagamento_divergente_vira_erro(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/pag/detPag/vPag", "1.00")

        assert "TOTAL-PAG-001" in _codigos(xml, Severidade.ERRO)

    def test_grupo_pag_ausente_e_pulado(self, xml_nfe: bytes) -> None:
        xml = sem_campo(xml_nfe, "NFe/infNFe/pag")
        relatorio = auditar_bytes(xml)

        assert "TOTAL-PAG-001" in {p.codigo for p in relatorio.puladas}

    def test_pagamento_sem_vpag_e_pulado(self, xml_nfe: bytes) -> None:
        xml = sem_campo(xml_nfe, "NFe/infNFe/pag/detPag/vPag")
        relatorio = auditar_bytes(xml)

        codigos_pulados = {p.codigo for p in relatorio.puladas}
        assert "TOTAL-PAG-001" in codigos_pulados

    def test_pagamento_unico_fora_de_detpag_e_aceito(self, xml_nfe: bytes) -> None:
        """Layout antigo traz `vPag` direto em `pag`; a regra precisa ler esse formato."""
        from tests.construir import transformar

        def mover_para_pag(raiz):
            corpo = next(e for e in raiz.iter() if e.tag.endswith("infNFe"))
            pag = next(e for e in corpo if e.tag.endswith("pag"))
            det = next(e for e in pag if e.tag.endswith("detPag"))
            valor = next(e for e in det if e.tag.endswith("vPag")).text
            pag.remove(det)
            from xml.etree import ElementTree as ET

            ET.SubElement(pag, "{http://www.portalfiscal.inf.br/nfe}vPag").text = valor

        xml = transformar(xml_nfe, mover_para_pag)

        assert "TOTAL-PAG-001" not in _codigos(xml, Severidade.ERRO)


class TestItemQuantidadeValor:
    def test_quantidade_vezes_unitario_divergente_vira_aviso(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/det/prod/vUnCom", "99.00")
        relatorio = auditar_bytes(xml)

        avisos = {a.codigo for a in relatorio.por_severidade(Severidade.AVISO)}
        infos = {a.codigo for a in relatorio.por_severidade(Severidade.INFO)}

        assert "TOTAL-ITEM-001" in avisos
        assert "TOTAL-ITEM-001" in infos, "o resumo do item precisa aparecer como informação"

    def test_item_coerente_nao_gera_achado(self, xml_nfe: bytes) -> None:
        assert "TOTAL-ITEM-001" not in _codigos(xml_nfe)


class TestPrestacaoCte:
    def test_vtprest_zero_vira_erro(self, xml_cte: bytes) -> None:
        xml = com_campo(xml_cte, "CTe/infCte/vPrest/vTPrest", "0.00")

        assert "CTE-PREST-001" in _codigos(xml, Severidade.ERRO)

    def test_vrec_maior_que_prestacao_vira_aviso(self, xml_cte: bytes) -> None:
        xml = com_campo(xml_cte, "CTe/infCte/vPrest/vRec", "999999.00")

        assert "CTE-PREST-001" in _codigos(xml, Severidade.AVISO)

    def test_soma_de_componentes_divergente_vira_aviso(self, xml_cte: bytes) -> None:
        xml = com_campo(xml_cte, "CTe/infCte/vPrest/Comp/vComp", "1.00")

        assert "CTE-PREST-001" in _codigos(xml, Severidade.AVISO)
