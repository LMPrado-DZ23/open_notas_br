"""Conversor do INI do ACBr: indireção `Usar=`, `?wsdl` e recusa de http.

Estes três pontos são o que faz a importação de 27/27 estar certa ou errada. Sem teste, uma
mudança futura no INI (ou no regex) quebraria a cobertura em silêncio — o importador aceitaria
e o número continuaria "27/27" apontando para URL errada.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

INI_EXEMPLO = """
[NFe_AC_P]
Usar=NFe_SVRS_P
URL-QRCode=http://www.sefaznet.ac.gov.br/nfce/qrcode

[NFe_SVRS_P]
NFeAutorizacao_4.00=https://nfe.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx?wsdl
NFeStatusServico_4.00=https://nfe.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx?wsdl
NFeRetAutorizacao_4.00=https://nfe.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx

[NFe_GO_P]
NfeAutorizacao_4.00=https://nfe.sefaz.go.gov.br/nfe/services/NFeAutorizacao4
"""


@pytest.fixture()
def conversor(tmp_path: Path, monkeypatch):
    ini = tmp_path / "ACBrNFeServicos.ini"
    ini.write_text(INI_EXEMPLO, encoding="latin-1")
    modulo = importlib.import_module("scripts.converter_acbr_nfe")
    monkeypatch.setattr(modulo, "INI", ini)
    return modulo


class TestResolucao:
    def test_segue_usar_ate_o_bloco_do_autorizador(self, conversor) -> None:
        secoes = conversor.ler_secoes()
        nome, bloco = conversor.resolver(secoes, "NFe_AC_P")
        assert nome == "NFe_SVRS_P", "AC não tem bloco próprio: precisa seguir Usar="
        assert "nfeautorizacao_4.00" in bloco

    def test_bloco_com_servico_nao_segue_adiante(self, conversor) -> None:
        secoes = conversor.ler_secoes()
        nome, _ = conversor.resolver(secoes, "NFe_GO_P")
        assert nome == "NFe_GO_P"

    def test_secao_inexistente_devolve_vazio(self, conversor) -> None:
        _, bloco = conversor.resolver(conversor.ler_secoes(), "NFe_XX_P")
        assert bloco == {}

    def test_cadeia_circular_nao_trava(self, conversor, tmp_path: Path) -> None:
        ini = tmp_path / "circ.ini"
        ini.write_text("[NFe_AC_P]\nUsar=NFe_XX_P\n[NFe_XX_P]\nUsar=NFe_AC_P\n", encoding="latin-1")
        conversor.INI = ini
        # O resolver tem teto de saltos: numa cadeia circular ele para e devolve o último
        # bloco (que só tem `usar`), em vez de girar para sempre.
        _, bloco = conversor.resolver(conversor.ler_secoes(), "NFe_AC_P")
        assert "usar" in bloco
        assert "nfeautorizacao_4.00" not in bloco


class TestLimpezaDeUrl:
    def test_remove_wsdl(self, conversor) -> None:
        # Enviar SOAP para o WSDL devolve erro de contrato, não de dados.
        assert conversor.limpar("https://x/y.asmx?wsdl") == "https://x/y.asmx"

    def test_url_sem_query_fica_igual(self, conversor) -> None:
        assert conversor.limpar("https://x/y") == "https://x/y"


class TestChaveCaseInsensitive:
    def test_chave_maiuscula_e_encontrada(self, conversor) -> None:
        # `NFeAutorizacao_4.00` e `NfeAutorizacao_4.00` coexistem no arquivo real.
        # Case-sensitive achava só 10 das 27 UFs.
        secoes = conversor.ler_secoes()
        bloco = secoes["NFe_SVRS_P"]
        assert "nfeautorizacao_4.00" in bloco
        bloco_go = secoes["NFe_GO_P"]
        assert "nfeautorizacao_4.00" in bloco_go
