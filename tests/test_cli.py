"""Testes da linha de comando: códigos de saída e formato de saída."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from notasbr.cli import (
    SAIDA_LEITURA,
    SAIDA_OK,
    SAIDA_REPROVADO,
    SAIDA_USO,
    main,
)
from tests.construir import com_campo, nfe


def escrever(tmp_path: Path, conteudo: bytes, nome: str = "nota.xml") -> Path:
    caminho = tmp_path / nome
    caminho.write_bytes(conteudo)
    return caminho


class TestAuditar:
    def test_documento_limpo_sai_com_zero(self, tmp_path: Path, capsys) -> None:
        caminho = escrever(tmp_path, nfe())
        assert main(["auditar", str(caminho)]) == SAIDA_OK
        saida = capsys.readouterr().out
        assert "APROVADO_COM_AVISOS" in saida or "APROVADO" in saida

    def test_documento_com_erro_sai_com_um(self, tmp_path: Path, capsys) -> None:
        caminho = escrever(tmp_path, com_campo(nfe(), "NFe/infNFe/ide/cDV", "9"))
        assert main(["auditar", str(caminho)]) == SAIDA_REPROVADO
        assert "CHAVE-CDV-001" in capsys.readouterr().out

    def test_json_e_consumivel(self, tmp_path: Path, capsys) -> None:
        caminho = escrever(tmp_path, nfe())
        assert main(["auditar", str(caminho), "--json"]) == SAIDA_OK
        dados = json.loads(capsys.readouterr().out)
        assert dados["schema"] == "notasbr.relatorio/1"
        assert dados["documento"]["tipo"] == "nfe"
        assert dados["resumo"]["erros"] == 0
        assert isinstance(dados["achados"], list)

    def test_lote_em_json(self, tmp_path: Path, capsys) -> None:
        a = escrever(tmp_path, nfe(), "a.xml")
        b = escrever(tmp_path, com_campo(nfe(), "NFe/infNFe/ide/cDV", "9"), "b.xml")
        codigo = main(["auditar", str(a), str(b), "--json"])
        assert codigo == SAIDA_REPROVADO
        dados = json.loads(capsys.readouterr().out)
        assert dados["total"] == 2
        assert len(dados["relatorios"]) == 2

    def test_estrito_reprova_por_aviso(self, tmp_path: Path) -> None:
        caminho = escrever(tmp_path, nfe())
        assert main(["auditar", str(caminho)]) == SAIDA_OK
        assert main(["auditar", str(caminho), "--estrito"]) == SAIDA_REPROVADO

    def test_arquivo_inexistente(self, tmp_path: Path) -> None:
        codigo = main(["auditar", str(tmp_path / "nada.xml")])
        assert codigo == SAIDA_USO

    def test_arquivo_que_nao_e_xml(self, tmp_path: Path) -> None:
        caminho = escrever(tmp_path, b"isto nao e xml", "lixo.xml")
        assert main(["auditar", str(caminho)]) == SAIDA_LEITURA

    def test_um_ruim_nao_impede_os_outros(self, tmp_path: Path, capsys) -> None:
        bom = escrever(tmp_path, nfe(), "bom.xml")
        ruim = escrever(tmp_path, b"<nada/>", "ruim.xml")
        codigo = main(["auditar", str(bom), str(ruim)])
        assert codigo == SAIDA_LEITURA
        saida = capsys.readouterr()
        assert "não auditado" in saida.err
        assert "APROVADO" in saida.out

    def test_verboso_mostra_limitacoes(self, tmp_path: Path, capsys) -> None:
        caminho = escrever(tmp_path, nfe())
        main(["auditar", str(caminho), "--verboso"])
        assert "limitações" in capsys.readouterr().out


class TestChave:
    def test_chave_valida(self, capsys) -> None:
        chave = "35250111222333000181550010000001231123456782"
        assert main(["chave", chave]) == SAIDA_OK
        assert "SP" in capsys.readouterr().out

    def test_chave_invalida(self, capsys) -> None:
        assert main(["chave", "123"]) == SAIDA_LEITURA
        assert "inválida" in capsys.readouterr().err

    def test_chave_json(self, capsys) -> None:
        chave = "35250111222333000181550010000001231123456782"
        assert main(["chave", chave, "--json"]) == SAIDA_OK
        assert json.loads(capsys.readouterr().out)["uf"] == "SP"


class TestDocumentos:
    def test_cnpj_valido(self) -> None:
        assert main(["cnpj", "11222333000181"]) == SAIDA_OK

    def test_cnpj_invalido(self) -> None:
        assert main(["cnpj", "11222333000182"]) == SAIDA_REPROVADO

    def test_cpf_valido(self) -> None:
        assert main(["cpf", "11144477735"]) == SAIDA_OK

    def test_cpf_invalido(self) -> None:
        assert main(["cpf", "11144477736"]) == SAIDA_REPROVADO


class TestRegras:
    def test_lista_catalogo(self, capsys) -> None:
        assert main(["regras"]) == SAIDA_OK
        saida = capsys.readouterr().out
        assert "CHAVE-DV-001" in saida
        assert "regra(s) registrada(s)" in saida

    def test_catalogo_json(self, capsys) -> None:
        assert main(["regras", "--json"]) == SAIDA_OK
        regras = json.loads(capsys.readouterr().out)
        assert len(regras) > 20
        assert all({"codigo", "descricao", "tipos"} <= set(r) for r in regras)


class TestVersao:
    def test_version(self, capsys) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--version"])
        assert excinfo.value.code == 0
        assert "notasbr" in capsys.readouterr().out
