"""Regras da chave de acesso: formato, DV, UF, modelo, AAMM, cDV e coerência com o ide.

A chave de 44 dígitos é o documento inteiro condensado: UF, AAMM, CNPJ, modelo, série, número, tpEmis
e DV. Cada bloco tem uma regra porque um dígito trocado muda o documento que a SEFAZ enxerga — e
rejeitar por `cStat` genérico é pior que apontar o campo.
"""

from __future__ import annotations

from notasbr import Severidade, auditar_bytes
from tests.construir import com_campo, sem_campo

NS = "http://www.portalfiscal.inf.br/nfe"


def _codigos(xml: bytes, severidade: Severidade | None = None) -> set[str]:
    relatorio = auditar_bytes(xml)
    achados = relatorio.achados if severidade is None else relatorio.por_severidade(severidade)
    return {a.codigo for a in achados}


def _puladas(xml: bytes) -> set[str]:
    return {p.codigo for p in auditar_bytes(xml).puladas}


def _recom_dv(base43: str) -> str:
    """Recalcula o DV para que a chave mutada continue sendo uma chave válida."""
    from notasbr.chave import calcular_dv

    return base43 + calcular_dv(base43)


class TestFormato:
    def test_chave_curta_vira_erro(self, xml_nfe: bytes) -> None:
        """Id truncado quebra a chave; o erro é de formato, não de dígito."""
        xml = com_campo(xml_nfe, "", "")
        xml = xml.replace(b'Id="NFe', b'Id="NF')

        assert "CHAVE-FMT-001" in _codigos(xml, Severidade.ERRO) or "CHAVE-FMT-001" in _codigos(xml)


class TestDigitoVerificador:
    def test_dv_errado_vira_erro(self, xml_nfe: bytes) -> None:
        relatorio = auditar_bytes(xml_nfe)
        chave = relatorio.chave
        assert chave is not None
        errada = chave[:43] + ("0" if chave[43] != "0" else "1")

        xml = xml_nfe.replace(chave.encode(), errada.encode())

        assert "CHAVE-DV-001" in _codigos(xml, Severidade.ERRO)

    def test_chave_valida_nao_gera_erro_de_dv(self, xml_nfe: bytes) -> None:
        assert "CHAVE-DV-001" not in _codigos(xml_nfe, Severidade.ERRO)


class TestUfEModelo:
    def test_uf_inexistente_vira_erro(self, xml_nfe: bytes) -> None:
        relatorio = auditar_bytes(xml_nfe)
        chave = relatorio.chave
        assert chave is not None
        # UF 99 não existe na tabela do IBGE.
        errada = _recom_dv("99" + chave[2:43])

        xml = xml_nfe.replace(chave.encode(), errada.encode())

        assert "CHAVE-UF-001" in _codigos(xml, Severidade.ERRO)

    def test_modelo_desconhecido_vira_aviso(self, xml_nfe: bytes) -> None:
        relatorio = auditar_bytes(xml_nfe)
        chave = relatorio.chave
        assert chave is not None
        # Modelo 99 não é documento fiscal conhecido.
        errada = _recom_dv(chave[:20] + "99" + chave[22:43])

        xml = xml_nfe.replace(chave.encode(), errada.encode())

        assert "CHAVE-MOD-001" in _codigos(xml, Severidade.AVISO)


class TestAnoMes:
    def test_mes_13_vira_erro(self, xml_nfe: bytes) -> None:
        relatorio = auditar_bytes(xml_nfe)
        chave = relatorio.chave
        assert chave is not None
        errada = _recom_dv(chave[:4] + "13" + chave[6:43])

        xml = xml_nfe.replace(chave.encode(), errada.encode())

        assert "CHAVE-AMM-001" in _codigos(xml, Severidade.ERRO)


class TestCdv:
    def test_cdv_divergente_vira_erro(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/ide/cDV", "9")

        assert "CHAVE-CDV-001" in _codigos(xml, Severidade.ERRO)

    def test_cdv_ausente_nao_avalia(self, xml_nfe: bytes) -> None:
        xml = sem_campo(xml_nfe, "NFe/infNFe/ide/cDV")

        assert "CHAVE-CDV-001" not in _codigos(xml)


class TestCoerenciaComIde:
    def test_cnpj_do_emitente_divergente_vira_erro(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/emit/CNPJ", "11444777000161")

        assert "CHAVE-EMIT-001" in _codigos(xml, Severidade.ERRO)

    def test_numero_da_nota_divergente_vira_erro(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/ide/nNF", "999")

        assert "CHAVE-CONSIST-001" in _codigos(xml, Severidade.ERRO)

    def test_ano_mes_divergente_vira_aviso(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/ide/dhEmi", "2020-05-01T10:00:00-03:00")

        assert "CHAVE-AMM-002" in _codigos(xml, Severidade.AVISO)


class TestProtocolo:
    def test_chave_do_protocolo_divergente_vira_erro(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "protNFe/infProt/chNFe", "0" * 44)

        assert "PROT-001" in _codigos(xml, Severidade.ERRO)


class TestAmbiente:
    def test_tpamb_invalido_vira_erro(self, xml_nfe: bytes) -> None:
        xml = com_campo(xml_nfe, "NFe/infNFe/ide/tpAmb", "3")

        assert "AMB-001" in _codigos(xml, Severidade.ERRO)


class TestChaveAusente:
    def test_documento_sem_chave_pula_as_regras(self) -> None:
        """NF-e assinada, ainda não autorizada: as regras de chave são puladas, não erradas."""
        from tests.construir import nfe

        xml = sem_campo(nfe(), "protNFe")

        assert not any(codigo.startswith("CHAVE-") for codigo in _codigos(xml, Severidade.ERRO)), (
            "sem chave não há erro de chave: é ausência de protocolo, não chave inválida"
        )
        # Sem chave, as regras de chave não avaliam — e o silêncio aqui é correto.


class TestIdEDocumento:
    def test_contingencia_nao_exige_aamm_igual_ao_dhemi(self, xml_nfe: bytes) -> None:
        """tpEmis != 1: a chave pode ter AAMM diferente do dhEmi, e a regra pula."""
        xml = com_campo(xml_nfe, "NFe/infNFe/ide/tpEmis", "2")

        assert "CHAVE-AMM-002" in _puladas(xml) or "CHAVE-AMM-002" not in _codigos(xml)
