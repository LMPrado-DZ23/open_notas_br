"""Ramos da CLI: chave ilegível, emitente com CPF, informação suprimida e falha de leitura.

O código de saída é contrato de automação; cada ramo aqui fixa um código e a mensagem que o
acompanha. Nenhum teste lê arquivo de verdade além do próprio `tmp_path`.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from notasbr import auditar_bytes
from notasbr.cli import SAIDA_LEITURA, SAIDA_REPROVADO, main
from notasbr.xml_util import local, navegar
from tests.construir import com_campo, nfe, transformar


def _escrever(tmp_path: Path, conteudo: bytes) -> Path:
    caminho = tmp_path / "nota.xml"
    caminho.write_bytes(conteudo)
    return caminho


def _chave_com_dv_errado(xml: bytes) -> bytes:
    """Troca o DV sem recalcular: a chave continua com 44 dígitos, mas não fecha."""
    chave = auditar_bytes(xml).chave
    assert chave is not None
    errada = chave[:43] + ("0" if chave[43] != "0" else "1")
    return xml.replace(chave.encode(), errada.encode())


def _trocar_documento(xml: bytes, grupo: str, tag: str, valor: str) -> bytes:
    def mutar(raiz: ET.Element) -> None:
        elemento = navegar(raiz, grupo)
        assert elemento is not None
        for filho in list(elemento):
            if local(filho.tag) in {"CNPJ", "CPF", "idEstrangeiro"}:
                elemento.remove(filho)
        novo = ET.SubElement(elemento, tag)
        novo.text = valor

    return transformar(xml, mutar)


class TestChaveIlegivel:
    def test_chave_que_nao_fecha_e_impressa_crua(self, tmp_path: Path, capsys) -> None:
        """Chave com DV inválido não é decomposta no cabeçalho: sai como veio, sem máscara."""
        xml = _chave_com_dv_errado(nfe())
        chave = auditar_bytes(xml).chave
        assert chave is not None
        caminho = _escrever(tmp_path, xml)

        assert main(["auditar", str(caminho)]) == SAIDA_REPROVADO

        saida = capsys.readouterr().out
        assert "CHAVE-DV-001" in saida
        # `formatada()` agruparia em blocos de 4 dígitos; a chave corrida prova o ramo de exceção.
        assert chave in saida


class TestEmitente:
    def test_cpf_do_emitente_aparece_formatado(self, tmp_path: Path, capsys) -> None:
        xml = _trocar_documento(nfe(), "NFe/infNFe/emit", "CPF", "11144477735")
        caminho = _escrever(tmp_path, xml)

        assert main(["auditar", str(caminho)]) == SAIDA_REPROVADO

        saida = capsys.readouterr().out
        assert "emitente:" in saida
        assert "111.444.777-35" in saida


class TestInformacao:
    def test_info_fica_oculto_sem_verboso(self, tmp_path: Path, capsys) -> None:
        """Desconto no total que não foi abatido do vNF rende TOTAL-COMPOSICAO-001 (info)."""
        xml = com_campo(nfe(), "NFe/infNFe/total/ICMSTot/vDesc", "100.00")
        caminho = _escrever(tmp_path, xml)

        main(["auditar", str(caminho)])
        sem_verboso = capsys.readouterr().out

        main(["auditar", str(caminho), "--verboso"])
        com_verboso = capsys.readouterr().out

        assert "TOTAL-COMPOSICAO-001" not in sem_verboso
        assert "TOTAL-COMPOSICAO-001" in com_verboso
        assert "INFO" in com_verboso


class TestFalhaDeLeitura:
    def test_oserror_vira_saida_de_leitura(self, tmp_path: Path, capsys, monkeypatch) -> None:
        """`OSError` ao ler não pode virar "aprovado" nem estourar a CLI.

        O erro é injetado porque o Windows não oferece um arquivo regular que passe em
        `Path.is_file()` e falhe em `read_bytes()` de forma portátil.
        """
        caminho = _escrever(tmp_path, nfe())

        def explodir(*args, **kwargs):
            raise OSError("disco indisponível")

        monkeypatch.setattr("notasbr.auditor.auditar_arquivo", explodir)

        codigo = main(["auditar", str(caminho)])

        assert codigo == SAIDA_LEITURA
        erro = capsys.readouterr().err
        assert "não foi possível ler o arquivo" in erro
        assert "disco indisponível" in erro
