"""Integridade dos XSD versionados: manifesto SHA-256 verificado no carregamento.

Seção R3 do v10.0 pede hash conferido no boot e aborto se divergir. Implementado de
forma **mais conservadora**, e o motivo é técnico:

- **Não aborta o boot.** Nem todo schema versionado aqui tem origem e versão
  oficialmente confirmadas (o PL_010h veio da referência canônica `sped-nfe`, não do
  ZIP do Portal Nacional). Derrubar a API por um schema não confirmado trocaria um
  risco de integridade por um risco de indisponibilidade — e o próprio v10.0 diz para
  não bloquear o sistema por schemas nessa condição.
- **Modo explícito**: `WARN` (padrão) registra divergência; `STRICT` levanta. Quem
  quiser o comportamento de aborto liga `STRICT` quando todos os schemas tiverem
  procedência confirmada.

O manifesto é gerado por `scripts/gerar_manifesto_xsd.py` e versionado, para que a
alteração de um schema apareça no diff do commit — não só na runtime.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)

MANIFESTO_PADRAO = Path("data/xsd_manifest.json")


class ModoVerificacao(StrEnum):
    WARN = "warn"
    STRICT = "strict"


class ErroDeIntegridade(Exception):
    """Hash divergente em modo STRICT, ou manifesto ilegível."""


@dataclass(frozen=True, slots=True)
class Divergencia:
    caminho: str
    esperado: str | None
    encontrado: str | None

    @property
    def tipo(self) -> str:
        if self.esperado is None:
            return "nao_manifestado"
        if self.encontrado is None:
            return "ausente"
        return "hash_divergente"


def sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(65536), b""):
            digest.update(bloco)
    return digest.hexdigest()


def carregar_manifesto(caminho: Path | str = MANIFESTO_PADRAO) -> dict[str, str]:
    """Lê o manifesto. Ausente é estado válido (verificação desligada)."""
    arquivo = Path(caminho)
    if not arquivo.is_file():
        return {}
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ErroDeIntegridade(f"manifesto ilegível: {arquivo}") from exc
    if not isinstance(dados, dict):
        raise ErroDeIntegridade("manifesto deve ser um objeto {caminho: sha256}")
    return {str(k): str(v) for k, v in dados.items()}


def verificar(
    raiz: Path | str,
    manifesto: dict[str, str],
    *,
    modo: ModoVerificacao = ModoVerificacao.WARN,
) -> list[Divergencia]:
    """Compara os arquivos sob `raiz` com o manifesto.

    Divergência inclui hash diferente, arquivo ausente e arquivo **não manifestado** —
    este último importa: um schema novo que ninguém registrou é tão suspeito quanto um
    alterado.
    """
    base = Path(raiz)
    if not base.is_dir():
        raise ErroDeIntegridade(f"diretório de schemas inexistente: {base}")

    encontrados: dict[str, str] = {}
    for arquivo in sorted(base.rglob("*")):
        if arquivo.is_file():
            # as_posix(): no Windows o separador e "\\" e o manifesto gerado aqui nao
            # casaria com o CI (Linux). Bug real, pego pelo teste de portabilidade.
            encontrados[arquivo.relative_to(base).as_posix()] = sha256(arquivo)

    divergencias: list[Divergencia] = []

    for relativo, hash_esperado in sorted(manifesto.items()):
        atual = encontrados.get(relativo)
        if atual is None:
            divergencias.append(Divergencia(relativo, hash_esperado, None))
        elif atual != hash_esperado:
            divergencias.append(Divergencia(relativo, hash_esperado, atual))

    for relativo in sorted(set(encontrados) - set(manifesto)):
        divergencias.append(Divergencia(relativo, None, encontrados[relativo]))

    if divergencias:
        resumo = "; ".join(f"{d.caminho} ({d.tipo})" for d in divergencias[:5])
        if modo is ModoVerificacao.STRICT:
            raise ErroDeIntegridade(f"hash de XSD não confere: {resumo}")
        logger.warning(
            "xsd_integridade_divergente",
            extra={"total": len(divergencias), "amostra": resumo},
        )
    return divergencias


def gerar_manifesto(raiz: Path | str) -> dict[str, str]:
    """Produz o manifesto a partir do diretório. Usado pelo script gerador."""
    base = Path(raiz)
    if not base.is_dir():
        raise ErroDeIntegridade(f"diretório de schemas inexistente: {base}")
    return {
        arquivo.relative_to(base).as_posix(): sha256(arquivo)
        for arquivo in sorted(base.rglob("*"))
        if arquivo.is_file()
    }
