"""Testes das regras de NF-e.

Cada caso parte de um fixture autoconsistente e aplica **uma** mutação, para que
o código esperado seja atribuível àquela mutação e a nada mais.
"""

from __future__ import annotations

import pytest

from notasbr import Severidade, auditar_bytes
from notasbr.auditor import LIMITACOES_PADRAO
from notasbr.erros import ArquivoGrandeDemais, DocumentoNaoSuportado, XmlInvalido
from notasbr.regras import REGRAS
from notasbr.regras.base import Regra
from tests.construir import com_atributo, com_campo, nfe, sem_campo, transformar


def codigos(xml: bytes, severidade: Severidade | None = None) -> set[str]:
    relatorio = auditar_bytes(xml)
    achados = relatorio.achados if severidade is None else relatorio.por_severidade(severidade)
    return {a.codigo for a in achados}


class TestDocumentoLimpo:
    def test_sem_erros(self, xml_nfe: bytes) -> None:
        relatorio = auditar_bytes(xml_nfe)
        assert relatorio.resumo.erros == 0, [a.to_dict() for a in relatorio.achados]

    def test_unico_aviso_e_a_ausencia_de_certificado(self, xml_nfe: bytes) -> None:
        relatorio = auditar_bytes(xml_nfe)
        assert [a.codigo for a in relatorio.achados] == ["ASSIN-005"]

    def test_verificacao_cripto_fica_explicitamente_pulada(self, xml_nfe: bytes) -> None:
        relatorio = auditar_bytes(xml_nfe)
        puladas = {p.codigo for p in relatorio.puladas}
        assert "ASSIN-004" in puladas
        motivo = next(p.motivo for p in relatorio.puladas if p.codigo == "ASSIN-004")
        assert "indisponível" in motivo or "X509Certificate" in motivo

    def test_metadados_do_relatorio(self, xml_nfe: bytes) -> None:
        relatorio = auditar_bytes(xml_nfe, arquivo="nota.xml")
        assert relatorio.tipo == "nfe"
        assert relatorio.raiz == "nfeProc"
        assert relatorio.versao_layout == "4.00"
        assert relatorio.modelo == "NF-e"
        assert relatorio.arquivo == "nota.xml"
        assert relatorio.ambiente == "Produção"
        assert relatorio.valor_total == "1000.00"
        assert relatorio.emitente["cnpj"] == "11.222.333/0001-81"
        assert relatorio.chave is not None and len(relatorio.chave) == 44
        assert relatorio.sha256 is not None and len(relatorio.sha256) == 64

    def test_limitacoes_viajam_no_relatorio(self, xml_nfe: bytes) -> None:
        relatorio = auditar_bytes(xml_nfe)
        assert relatorio.limitacoes == list(LIMITACOES_PADRAO)
        assert any("XSD" in limitacao for limitacao in relatorio.limitacoes)

    def test_dois_itens_somam_certo(self) -> None:
        relatorio = auditar_bytes(nfe(dois_itens=True))
        assert relatorio.resumo.erros == 0
        assert relatorio.valor_total == "2000.00"


class TestChave:
    def test_numero_divergente(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/ide/nNF", "999")
        assert "CHAVE-CONSIST-001" in codigos(xml, Severidade.ERRO)

    def test_uf_divergente(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/ide/cUF", "33")
        assert "CHAVE-CONSIST-001" in codigos(xml, Severidade.ERRO)

    def test_cdv_divergente(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/ide/cDV", "9")
        assert "CHAVE-CDV-001" in codigos(xml, Severidade.ERRO)

    def test_emitente_divergente(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/emit/CNPJ", "11444777000161")
        assert "CHAVE-EMIT-001" in codigos(xml, Severidade.ERRO)

    def test_dv_invalido_na_propria_chave(self) -> None:
        xml = com_atributo(nfe(), "NFe/infNFe", "Id", "NFe" + "1" * 44)
        assert "CHAVE-DV-001" in codigos(xml, Severidade.ERRO)

    def test_id_vazio_cai_para_o_protocolo_e_acusa_divergencia(self) -> None:
        xml = com_atributo(nfe(), "NFe/infNFe", "Id", "")
        assert "CHAVE-ID-001" in codigos(xml, Severidade.ERRO)

    def test_protocolo_com_outra_chave(self) -> None:
        xml = com_campo(nfe(), "protNFe/infProt/chNFe", "0" * 44)
        assert "PROT-001" in codigos(xml, Severidade.ERRO)

    def test_sem_id_e_sem_protocolo(self) -> None:
        xml = com_atributo(nfe(com_protocolo=False), "NFe/infNFe", "Id", "")
        assert "CHAVE-FMT-001" in codigos(xml, Severidade.ERRO)


class TestTotais:
    def test_vprod_total_errado(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/total/ICMSTot/vProd", "999.00")
        achados = [a for a in auditar_bytes(xml).por_severidade(Severidade.ERRO)]
        assert any(a.codigo == "TOTAL-VPROD-001" for a in achados)

    def test_soma_dos_itens_errada_aponta_o_item(self) -> None:
        xml = com_campo(nfe(dois_itens=True), "NFe/infNFe/det/prod/vProd", "999.00")
        relatorio = auditar_bytes(xml)
        assert any(a.codigo == "TOTAL-VPROD-001" for a in relatorio.por_severidade(Severidade.ERRO))
        assert any(
            a.codigo == "TOTAL-ITEM-001" and "det[1]" in a.caminho for a in relatorio.achados
        )

    def test_pagamento_nao_fecha(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/pag/detPag/vPag", "1.00")
        assert "TOTAL-PAG-001" in codigos(xml, Severidade.ERRO)

    def test_vnf_zero(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/total/ICMSTot/vNF", "0.00")
        xml = com_campo(xml, "NFe/infNFe/pag/detPag/vPag", "0.00")
        assert "TOTAL-VNF-001" in codigos(xml, Severidade.ERRO)

    def test_troco_e_considerado(self) -> None:
        # vPag de 1100 com 100 de troco fecha com vNF de 1000.
        xml = com_campo(nfe(), "NFe/infNFe/pag/detPag/vPag", "1100.00")
        xml = transformar(
            xml,
            lambda raiz: _adicionar(raiz, "NFe/infNFe/pag", "vTroco", "100.00"),
        )
        assert "TOTAL-PAG-001" not in codigos(xml, Severidade.ERRO)


def _adicionar(raiz, caminho_pai: str, tag: str, texto: str) -> None:
    from notasbr.xml_util import navegar

    pai = navegar(raiz, caminho_pai)
    assert pai is not None
    elemento = pai.makeelement(tag, {})
    elemento.text = texto
    pai.append(elemento)


class TestTributos:
    def test_cfop_com_letra(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/det/prod/CFOP", "51O2")
        assert "TRIB-CFOP-001" in codigos(xml, Severidade.ERRO)

    def test_cfop_de_grupo_inexistente(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/det/prod/CFOP", "9102")
        assert "TRIB-CFOP-001" in codigos(xml, Severidade.ERRO)

    def test_cfop_de_entrada_em_nota_de_saida(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/det/prod/CFOP", "1102")
        assert "TRIB-CFOP-002" in codigos(xml, Severidade.ERRO)

    def test_ncm_curto(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/det/prod/NCM", "123")
        assert "TRIB-NCM-001" in codigos(xml, Severidade.AVISO)

    def test_cst_inexistente(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/det/imposto/ICMS/ICMS00/CST", "77")
        assert "TRIB-ICMS-001" in codigos(xml, Severidade.ERRO)

    def test_crt_invalido(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/emit/CRT", "9")
        assert "TRIB-CRT-001" in codigos(xml, Severidade.ERRO)

    def test_simples_nacional_com_cst_gera_aviso(self) -> None:
        # CRT=1 (Simples) deveria usar CSOSN, mas o fixture traz CST 00.
        xml = com_campo(nfe(), "NFe/infNFe/emit/CRT", "1")
        assert "TRIB-CRT-001" in codigos(xml, Severidade.AVISO)

    def test_sem_pis_e_cofins(self) -> None:
        xml = sem_campo(nfe(), "NFe/infNFe/det/imposto/PIS")
        assert "TRIB-PIS-COFINS-001" in codigos(xml, Severidade.AVISO)


class TestEstrutura:
    def test_sem_assinatura(self) -> None:
        xml = sem_campo(nfe(), "NFe/Signature")
        assert "ASSIN-001" in codigos(xml, Severidade.ERRO)

    def test_sem_natop(self) -> None:
        xml = sem_campo(nfe(), "NFe/infNFe/ide/natOp")
        assert "OBRIG-ide-natOp" in codigos(xml, Severidade.ERRO)

    def test_sem_itens(self) -> None:
        xml = sem_campo(nfe(), "NFe/infNFe/det")
        assert "DOC-ITENS-001" in codigos(xml, Severidade.ERRO)

    def test_nitem_fora_de_sequencia(self) -> None:
        def trocar(raiz) -> None:
            from notasbr.xml_util import filhos

            inf = None
            for elemento in raiz.iter():
                if elemento.tag.endswith("infNFe"):
                    inf = elemento
            assert inf is not None
            itens = filhos(inf, "det")
            itens[1].set("nItem", "7")

        xml = transformar(nfe(dois_itens=True), trocar)
        assert "NFE-DET-001" in codigos(xml, Severidade.ERRO)

    def test_namespace_errado(self) -> None:
        # Troca o namespace default nos bytes: o parse então vê tags em outro
        # namespace, que é o cenário real de documento remontado com namespace errado.
        xml = nfe().replace(b'xmlns="http://www.portalfiscal.inf.br/nfe"', b'xmlns="urn:errado"')
        assert "DOC-NS-001" in codigos(xml, Severidade.ERRO)

    def test_versao_desconhecida_gera_aviso(self) -> None:
        xml = com_atributo(nfe(), "NFe/infNFe", "versao", "9.99")
        assert "DOC-VER-001" in codigos(xml, Severidade.AVISO)

    def test_ambiente_invalido(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/ide/tpAmb", "3")
        assert "AMB-001" in codigos(xml, Severidade.ERRO)

    def test_ambiente_divergente_do_protocolo(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/ide/tpAmb", "2")
        # tpAmb do documento muda, o do protocolo continua 1: inconsistência real.
        assert "AMB-001" in codigos(xml, Severidade.ERRO)

    def test_dest_sem_indiedest(self) -> None:
        xml = sem_campo(nfe(), "NFe/infNFe/dest/indIEDest")
        assert "NFE-DEST-001" in codigos(xml, Severidade.ERRO)


class TestEntradasInvalidas:
    def test_lote_nao_e_auditado(self) -> None:
        with pytest.raises(DocumentoNaoSuportado, match="lote"):
            auditar_bytes(b'<enviNFe versao="4.00"><NFe/></enviNFe>')

    def test_raiz_desconhecida(self) -> None:
        with pytest.raises(DocumentoNaoSuportado, match="não é um documento"):
            auditar_bytes(b"<qualquer><coisa/></qualquer>")

    def test_xml_com_dtd(self) -> None:
        with pytest.raises(XmlInvalido):
            auditar_bytes(b'<!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>')

    def test_limite_de_bytes(self) -> None:
        with pytest.raises(ArquivoGrandeDemais):
            auditar_bytes(nfe(), limite_bytes=100)

    def test_evento_nao_e_auditado(self) -> None:
        with pytest.raises(DocumentoNaoSuportado, match="evento"):
            auditar_bytes(b"<procEventoNFe><evento/></procEventoNFe>")


class TestRedeDeSeguranca:
    def test_regra_que_quebra_vira_erro_e_nao_aprovacao(self, xml_nfe: bytes) -> None:
        def quebrar(_contexto) -> None:
            raise RuntimeError("falha proposital")

        regra_quebrada = Regra("TESTE-999", "regra que quebra", ("nfe",), quebrar)
        REGRAS.append(regra_quebrada)
        try:
            relatorio = auditar_bytes(xml_nfe)
        finally:
            REGRAS.remove(regra_quebrada)

        assert not relatorio.aprovado
        achado = next(a for a in relatorio.achados if a.codigo == "MOTOR-001")
        assert achado.severidade is Severidade.ERRO
        assert "TESTE-999" in achado.mensagem
