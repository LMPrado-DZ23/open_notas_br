"""O scanner de segredos precisa detectar, não vazar e não gritar falso positivo.

Um scanner que só passa no repositório atual não prova nada — pode estar cego. Estes testes
plantam segredos sintéticos e verificam: (a) o achado aparece; (b) o relatório **não** repete o
valor, senão o log do CI vira o segundo vazamento; (c) fixture de teste com senha fictícia não é
bloqueada.
"""

from __future__ import annotations

import pytest
from scripts import verificar_segredos as segredos

CHAVE_FALSA = "-----BEGIN " + "RSA PRIVATE KEY-----"
TOKEN_FALSO = "ghp_" + "a" * 36


class TestDeteccao:
    @pytest.mark.parametrize(
        ("linha", "regra"),
        [
            (CHAVE_FALSA, "chave_privada"),
            (f'token = "{TOKEN_FALSO}"', "token_github"),
            ('aws = "AKIA' + "B" * 16 + '"', "chave_aws"),
            ('api_key = "sk-' + "c" * 40 + '"', "token_openai"),
            ('senha_db = "supersecreta123"', "senha_literal"),
        ],
    )
    def test_detecta_o_padrao(self, linha: str, regra: str) -> None:
        achados = list(segredos.varrer_texto("app/modulo.py", linha + "\n"))
        assert [a.regra for a in achados] == [regra]

    def test_texto_limpo_nao_gera_achado(self) -> None:
        limpo = "def somar(a: int, b: int) -> int:\n    return a + b\n"
        assert list(segredos.varrer_texto("app/modulo.py", limpo)) == []


class TestSigiloDoRelatorio:
    def test_relatorio_nao_repeto_o_valor_encontrado(self) -> None:
        achados = list(segredos.varrer_texto("app/modulo.py", f'token = "{TOKEN_FALSO}"'))
        assert len(achados) == 1
        texto = str(achados[0])
        assert "app/modulo.py:1" in texto
        assert TOKEN_FALSO not in texto, "o relatorio nao pode repassar o segredo adiante"

    def test_saida_do_comando_nao_contem_o_segredo(self, tmp_path, capsys) -> None:
        alvo = tmp_path / "vazou.py"
        alvo.write_text(f'chave = "{CHAVE_FALSA}"\n', encoding="utf-8")

        codigo = segredos.main([str(alvo)])

        assert codigo == 1
        saida = capsys.readouterr().out
        assert "vazou.py:1" in saida
        assert "PRIVATE KEY" not in saida


class TestDispensa:
    def test_senha_de_teste_em_fixture_nao_bloqueia(self) -> None:
        # `tests/` usa senhas fictícias de propósito (gerar_pfx). Só a regra de senha literal
        # é dispensada ali; chave privada e token continuam proibidos.
        linha = 'SENHA = b"senha-de-teste"\n'
        assert list(segredos.varrer_texto("tests/test_algo.py", linha)) == []

    def test_chave_privada_em_teste_continua_proibida(self) -> None:
        achados = list(segredos.varrer_texto("tests/test_algo.py", CHAVE_FALSA + "\n"))
        assert [a.regra for a in achados] == ["chave_privada"]


class TestRepositorioAtual:
    def test_repositorio_nao_tem_segredo(self) -> None:
        achados = segredos.varrer(segredos.arquivos_versionados())
        assert achados == [], "\n".join(str(a) for a in achados)
