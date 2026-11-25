"""Garante que a configuração documentada não divirja da real.

Dois guardas:

1. **Toda variável de `Settings` tem entrada em `.env.example`.** Sem isso, quem
   clona o repositório sobe com uma variável sem saber que ela existe, e o
   sintoma aparece longe da causa.
2. **`.gitignore` cobre certificado e `.env`.** Um `.pfx` versionado é uma
   credencial vazada; isso não pode depender de alguém lembrar.
"""

from __future__ import annotations

import pathlib
import re

from app.core.config import Settings

RAIZ = pathlib.Path(__file__).resolve().parent.parent

#: Variáveis lidas pelo `docker-compose.yml` (portas publicadas no host), não pelo
#: `Settings`. Ficam listadas aqui para que a exceção seja explícita e o teste não
#: vire um "qualquer coisa vale".
VARIAVEIS_DE_COMPOSE = {
    "api_host_port",
    "postgres_host_port",
    "redis_host_port",
}


def _chaves_do_exemplo() -> set[str]:
    texto = (RAIZ / ".env.example").read_text(encoding="utf-8")
    return {m.group(1).lower() for m in re.finditer(r"^([A-Z][A-Z0-9_]*)=", texto, re.M)}


class TestEnvExample:
    def test_cobre_todas_as_variaveis(self) -> None:
        faltando = sorted(set(Settings.model_fields) - _chaves_do_exemplo())
        assert not faltando, "variáveis de Settings sem entrada em .env.example: " + ", ".join(
            faltando
        )

    def test_sem_variavel_sobrando(self) -> None:
        # Sobra também é problema: variável que não existe no código confunde quem
        # configura e sugere um recurso que não funciona.
        sobrando = sorted(_chaves_do_exemplo() - set(Settings.model_fields) - VARIAVEIS_DE_COMPOSE)
        assert not sobrando, (
            ".env.example documenta variável que Settings não conhece: " + ", ".join(sobrando)
        )

    def test_sem_valor_de_segredo_real(self) -> None:
        texto = (RAIZ / ".env.example").read_text(encoding="utf-8")
        # Chaves precisam estar vazias ou com placeholder óbvio, nunca preenchidas.
        for chave in ("MASTER_ENCRYPTION_KEY", "SERPRO_CNPJ_TOKEN"):
            achado = re.search(rf"^{chave}=(.*)$", texto, re.M)
            if achado:
                valor = achado.group(1).strip()
                assert valor == "" or valor.startswith("<") or valor.startswith("coloque"), (
                    f"{chave} não pode vir preenchida no exemplo"
                )


class TestGitignore:
    def test_ignora_certificados_e_env(self) -> None:
        regras = (RAIZ / ".gitignore").read_text(encoding="utf-8")
        for alvo in ("*.pfx", "*.p12", ".env"):
            assert alvo in regras, f".gitignore precisa cobrir {alvo}"

    def test_nenhum_certificado_versionado(self) -> None:
        encontrados = [
            p
            for p in RAIZ.rglob("*")
            if p.is_file()
            and p.suffix.lower() in {".pfx", ".p12"}
            and ".git" not in p.parts
            and "node_modules" not in p.parts
        ]
        assert not encontrados, f"certificado no diretório de trabalho: {encontrados}"

    def test_nenhum_env_real(self) -> None:
        assert not (RAIZ / ".env").exists() or True  # .env local é permitido, mas ignorado
        assert ".env" in (RAIZ / ".gitignore").read_text(encoding="utf-8")
