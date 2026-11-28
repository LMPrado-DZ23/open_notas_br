"""Ramos de tributos, totais, cadastros, modelos e chave que faltavam cobertura.

Aqui estão os desfechos em que a regra **não** produz achado por ausência de dado — e por isso
precisam de teste: um silêncio não intencional é o que separa "aprovado" de "não olhei". O caso
de `prod/CFOP` é o exemplo vivo: o comentário da regra diz que a obrigatoriedade cobre a
ausência, mas `OBRIGATORIOS` só lista campos de `ide`, `emit` e `total`.

O restante são contratos diretos de funções públicas (`cadastros`, `Resumo`, `ChaveAcesso`).
"""

from __future__ import annotations

from dataclasses import replace
from xml.etree import ElementTree as ET

import pytest

from notasbr import Severidade, auditar_bytes
from notasbr.cadastros import dv_cpf, formatar_cpf, normalizar_cpf
from notasbr.chave import ChaveAcesso
from notasbr.modelos import Resumo
from notasbr.xml_util import local, navegar
from tests.construir import cte, nfe, sem_campo, transformar


def _codigos(relatorio, severidade: Severidade | None = None) -> set[str]:
    achados = relatorio.achados if severidade is None else relatorio.por_severidade(severidade)
    return {a.codigo for a in achados}


class TestCfopAusente:
    def test_item_sem_cfop_nao_produz_achado(self) -> None:
        """`prod/CFOP` ausente não gera nem TRIB-CFOP-001 nem 002.

        O código comenta que "OBRIG cobre ausência nos campos obrigatórios", mas
        `OBRIGATORIOS["nfe"]` não inclui campos de item. Comportamento atual: silêncio.
        """
        xml = sem_campo(nfe(), "NFe/infNFe/det/prod/CFOP")

        relatorio = auditar_bytes(xml)

        assert "TRIB-CFOP-001" not in _codigos(relatorio)
        assert "TRIB-CFOP-002" not in _codigos(relatorio)
        assert not [a for a in relatorio.achados if "CFOP" in a.codigo]

    def test_tpnf_ausente_nao_avalia_sentido(self) -> None:
        """Sem `tpNF` não há sentido de operação para comparar: TRIB-CFOP-002 não avalia."""
        xml = sem_campo(nfe(), "NFe/infNFe/ide/tpNF")
        relatorio = auditar_bytes(xml)

        assert "TRIB-CFOP-002" not in _codigos(relatorio)
        assert "OBRIG-ide-tpNF" in _codigos(relatorio, Severidade.ERRO)


class TestIcmsESemGrupo:
    def test_item_sem_imposto_vira_erro_nas_duas_regras(self) -> None:
        """Sem `imposto` no item, ICMS e PIS/COFINS apontam o fato, cada uma do seu jeito."""

        def mutar(raiz: ET.Element) -> None:
            item = navegar(raiz, "NFe/infNFe/det")
            assert item is not None
            for filho in list(item):
                if local(filho.tag) == "imposto":
                    item.remove(filho)

        xml = transformar(nfe(), mutar)
        erros = _codigos(auditar_bytes(xml), Severidade.ERRO)

        assert "TRIB-ICMS-001" in erros
        assert "TRIB-PIS-COFINS-001" in erros

    def test_grupo_sem_cst_nem_csosn_vira_erro(self) -> None:
        """Grupo concreto (ICMS00) sem `CST` e sem `CSOSN`: erro, não aviso de tabela."""

        def mutar(raiz: ET.Element) -> None:
            grupo = navegar(raiz, "NFe/infNFe/det/imposto/ICMS/ICMS00")
            assert grupo is not None
            for filho in list(grupo):
                if local(filho.tag) == "CST":
                    grupo.remove(filho)

        xml = transformar(nfe(), mutar)
        achados = [a for a in auditar_bytes(xml).achados if a.codigo == "TRIB-ICMS-001"]

        assert any("sem CST nem CSOSN" in a.mensagem for a in achados)
        assert all(a.severidade is Severidade.ERRO for a in achados)


class TestPrestacaoCte:
    def test_sem_vtprest_pula_prestacao(self) -> None:
        xml = sem_campo(cte(), "CTe/infCte/vPrest/vTPrest")
        relatorio = auditar_bytes(xml)

        assert "CTE-PREST-001" in {p.codigo for p in relatorio.puladas}
        motivo = next(p.motivo for p in relatorio.puladas if p.codigo == "CTE-PREST-001")
        assert "vTPrest ausente" in motivo

    def test_sem_componentes_nao_compara_soma(self) -> None:
        """Sem nenhum `Comp` não existe soma a comparar: a regra não inventa divergência."""

        def mutar(raiz: ET.Element) -> None:
            grupo = navegar(raiz, "CTe/infCte/vPrest")
            assert grupo is not None
            for filho in list(grupo):
                if local(filho.tag) == "Comp":
                    grupo.remove(filho)

        xml = transformar(cte(), mutar)

        assert "CTE-PREST-001" not in _codigos(auditar_bytes(xml))


class TestCadastros:
    def test_normalizar_cpf_remove_mascara(self) -> None:
        assert normalizar_cpf("111.444.777-35") == "11144477735"
        assert normalizar_cpf(None) == ""

    def test_dv_cpf_exige_nove_digitos(self) -> None:
        with pytest.raises(ValueError, match="9 dígitos"):
            dv_cpf("123")

    def test_formatar_cpf_devolve_bruto_fora_de_onze_digitos(self) -> None:
        assert formatar_cpf("123") == "123"
        assert formatar_cpf("11144477735") == "111.444.777-35"


class TestResumo:
    @pytest.mark.parametrize(
        ("contadores", "esperado"),
        [
            ({}, "aprovado"),
            ({"informacoes": 3}, "aprovado"),
            ({"avisos": 1}, "aprovado_com_avisos"),
            ({"erros": 1}, "reprovado"),
            ({"erros": 1, "avisos": 1}, "reprovado"),
        ],
    )
    def test_situacao(self, contadores: dict[str, int], esperado: str) -> None:
        """Informação não muda a situação; aviso muda; erro vence o aviso."""
        assert Resumo(**contadores).situacao == esperado


class TestChaveDireta:
    def test_serie_nao_numerica_nao_quebra_leitura(self) -> None:
        """`serie_int` é leitura tolerante: série não numérica devolve `None`, sem exceção."""
        chave = ChaveAcesso.parse("35250111222333000181550010000001231123456782")

        assert replace(chave, serie="007").serie_int == 7
        assert replace(chave, serie="A1").serie_int is None
