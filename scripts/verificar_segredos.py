"""Varre os arquivos versionados atrás de segredo acidental.

Existe porque o projeto tem uma regra dura (nunca versionar API key, certificado, PFX/PEM, token ou
senha) e, até aqui, **nenhuma verificação automática** a sustentava: só disciplina. O CI não tinha
secret scanning.

Decisões:

- **Sem dependência nova** (regra 11): `gitleaks`/`trufflehog` resolveriam, mas são binários
  externos. O que este projeto precisa detectar é um conjunto pequeno e estável de formas.
- **Não ecoa o segredo.** O relatório diz caminho, linha e o *tipo* do achado. Imprimir o valor
  transformaria o relatório do CI num segundo vazamento.
- **`tests/` e `docs/` ficam fora da regra de "senha literal"**, e apenas dela: testes usam
  `"senha-de-teste"` de propósito. PEM e token continuam proibidos em qualquer caminho.

Uso:
    python -m scripts.verificar_segredos            # varre o índice do git
    python -m scripts.verificar_segredos arquivo…   # varre caminhos específicos
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Caminhos onde senha literal é legítima (fixture de teste e exemplo de documentação).
#: Só a regra `senha_literal` é dispensada; PEM e token valem em todo lugar.
_DISPENSA_SENHA_LITERAL = ("tests/", "docs/", "scripts/demo_e2e.py")

#: Tamanho máximo por arquivo: nada de varrer dump de 1 GB.
TAMANHO_MAXIMO = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Regra:
    nome: str
    padrao: re.Pattern[str]
    descricao: str


REGRAS: tuple[Regra, ...] = (
    Regra(
        "chave_privada",
        re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
        "bloco PEM de chave privada",
    ),
    Regra(
        "token_github",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
        "token de acesso do GitHub",
    ),
    Regra(
        "token_openai",
        re.compile(r"\bsk-[A-Za-z0-9]{32,}"),
        "chave de API no formato sk-",
    ),
    Regra(
        "chave_aws",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "access key id da AWS",
    ),
    Regra(
        "pfx_embutido",
        re.compile(r"(?i)(pfx|pkcs12?)\s*[:=]\s*['\"][A-Za-z0-9+/]{60,}"),
        "PKCS#12 embutido em literal",
    ),
    Regra(
        "senha_literal",
        # Aceita sufixo (`senha_db`, `api_key_producao`): `\bsenha\b` não casa em `senha_db`
        # porque `_` é caractere de palavra. Foi assim que o primeiro teste falhou.
        re.compile(
            r"(?i)\b(?:senha|password|passwd|secret|api[_-]?key|apikey|token)[a-z0-9_]*\s*"
            r"[:=]\s*['\"][^'\"\s]{8,}['\"]"
        ),
        "senha ou token em literal",
    ),
)


@dataclass(frozen=True, slots=True)
class Achado:
    caminho: str
    linha: int
    regra: str
    descricao: str

    def __str__(self) -> str:
        # Só caminho/linha/tipo: o valor encontrado NUNCA entra aqui.
        return f"{self.caminho}:{self.linha}: {self.descricao}"


def _dispensada(regra: Regra, caminho: str) -> bool:
    return regra.nome == "senha_literal" and caminho.replace("\\", "/").startswith(
        _DISPENSA_SENHA_LITERAL
    )


def varrer_texto(caminho: str, texto: str) -> Iterator[Achado]:
    """Achados de um conteúdo já lido.

    Uma regra por linha, da mais específica para a mais genérica: `token = "ghp_..."` casa com
    `token_github` **e** com `senha_literal`, e reportar duas vezes o mesmo valor só polui o
    relatório. A primeira que casa vence.
    """
    for numero, linha in enumerate(texto.splitlines(), start=1):
        for regra in REGRAS:
            if _dispensada(regra, caminho):
                continue
            if regra.padrao.search(linha):
                yield Achado(caminho, numero, regra.nome, regra.descricao)
                break


def varrer_arquivo(caminho: Path, *, relativo: str | None = None) -> Iterator[Achado]:
    nome = relativo or str(caminho)
    try:
        if caminho.stat().st_size > TAMANHO_MAXIMO:
            return
        bruto = caminho.read_bytes()
    except OSError:
        return
    if b"\x00" in bruto[:4096]:  # binário: PFX, imagem, zip
        return
    texto = bruto.decode("utf-8", errors="replace")
    yield from varrer_texto(nome, texto)


def arquivos_versionados(raiz: Path = RAIZ) -> list[tuple[Path, str]]:
    """Arquivos do índice do git, como (caminho absoluto, caminho relativo)."""
    saida = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=raiz,
        capture_output=True,
        check=True,
    ).stdout
    relativos = [p for p in saida.decode("utf-8").split("\0") if p]
    return [(raiz / rel, rel) for rel in relativos]


def varrer(caminhos: Iterable[tuple[Path, str]]) -> list[Achado]:
    achados: list[Achado] = []
    for caminho, relativo in caminhos:
        achados.extend(varrer_arquivo(caminho, relativo=relativo))
    return achados


def main(argv: Sequence[str] | None = None) -> int:
    argumentos = list(sys.argv[1:] if argv is None else argv)
    alvos = (
        [(Path(argumento), argumento) for argumento in argumentos]
        if argumentos
        else arquivos_versionados()
    )

    achados = varrer(alvos)
    if not achados:
        print(f"nenhum segredo em {len(alvos)} arquivo(s) verificado(s)")
        return 0

    print(f"{len(achados)} achado(s):")
    for achado in achados:
        print(f"  {achado}")
    print(
        "\nRemova o valor do arquivo e rotacione o segredo: estar no histórico do git já conta "
        "como exposto."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
