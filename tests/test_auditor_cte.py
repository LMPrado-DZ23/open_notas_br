"""Testes das regras de CT-e."""

from __future__ import annotations

import pytest

from notasbr import Severidade, auditar_bytes
from notasbr.erros import DocumentoNaoSuportado
from tests.construir import com_campo, cte, sem_campo, transformar


def codigos(xml: bytes, severidade: Severidade | None = None) -> set[str]:
    relatorio = auditar_bytes(xml)
    achados = relatorio.achados if severidade is None else relatorio.por_severidade(severidade)
    return {a.codigo for a in achados}


class TestDocumentoLimpo:
    def test_sem_erros(self, xml_cte: bytes) -> None:
        relatorio = auditar_bytes(xml_cte)
        assert relatorio.resumo.erros == 0, [a.to_dict() for a in relatorio.achados]

    def test_metadados(self, xml_cte: bytes) -> None:
        relatorio = auditar_bytes(xml_cte)
        assert relatorio.tipo == "cte"
        assert relatorio.raiz == "cteProc"
        assert relatorio.modelo == "CT-e"
        assert relatorio.valor_total == "1500.00"
        assert relatorio.chave is not None and relatorio.chave[20:22] == "57"


class TestRegras:
    def test_cfop_inexistente(self) -> None:
        xml = com_campo(cte(), "CTe/infCte/ide/CFOP", "1353")
        # 1353 é CFOP válido de entrada; o CT-e aqui é de serviço, mas a regra é de forma.
        assert "TRIB-CFOP-001" not in codigos(xml, Severidade.ERRO)

    def test_cfop_com_tres_digitos(self) -> None:
        xml = com_campo(cte(), "CTe/infCte/ide/CFOP", "535")
        assert "TRIB-CFOP-001" in codigos(xml, Severidade.ERRO)

    def test_valor_da_prestacao_zero(self) -> None:
        xml = com_campo(cte(), "CTe/infCte/vPrest/vTPrest", "0.00")
        assert "CTE-PREST-001" in codigos(xml, Severidade.ERRO)

    def test_vrec_maior_que_prestacao(self) -> None:
        xml = com_campo(cte(), "CTe/infCte/vPrest/vRec", "9999.00")
        assert "CTE-PREST-001" in codigos(xml, Severidade.AVISO)

    def test_componentes_nao_somam(self) -> None:
        xml = com_campo(cte(), "CTe/infCte/vPrest/Comp/vComp", "10.00")
        assert "CTE-PREST-001" in codigos(xml, Severidade.AVISO)

    def test_sem_infctenorm(self) -> None:
        xml = sem_campo(cte(), "CTe/infCte/infCTeNorm")
        assert "DOC-ITENS-001" in codigos(xml, Severidade.ERRO)

    def test_sem_assinatura(self) -> None:
        xml = sem_campo(cte(), "CTe/Signature")
        assert "ASSIN-001" in codigos(xml, Severidade.ERRO)

    def test_numero_divergente_da_chave(self) -> None:
        xml = com_campo(cte(), "CTe/infCte/ide/nCT", "999")
        assert "CHAVE-CONSIST-001" in codigos(xml, Severidade.ERRO)

    def test_chave_de_nfe_em_documento_cte(self) -> None:
        """Uma chave com modelo 55 dentro de um CT-e deve ser recusada."""

        def trocar_modelo(raiz) -> None:
            from notasbr.chave import montar_chave
            from notasbr.xml_util import navegar

            inf = navegar(raiz, "CTe/infCte")
            assert inf is not None
            chave_nfe = montar_chave(
                c_uf="35",
                aamm="2501",
                cnpj="11222333000181",
                modelo="55",
                serie="1",
                numero="456",
                tp_emis="1",
                c_nf="12345678",
            )
            inf.set("Id", f"CTe{chave_nfe}")

        xml = transformar(cte(), trocar_modelo)
        assert "CHAVE-MOD-001" in codigos(xml, Severidade.ERRO)


class TestEntradasInvalidas:
    def test_sem_infcte(self) -> None:
        with pytest.raises(DocumentoNaoSuportado, match="infCte"):
            auditar_bytes(b'<CTe versao="4.00"><NFe/></CTe>')
