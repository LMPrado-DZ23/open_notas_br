"""Seed de municípios a partir da API oficial do IBGE.

Fonte: `https://servicodados.ibge.gov.br/api/v1/localidades/municipios` (oficial, R3).

Dois modos, de propósito:

- `--cache data/ibge_municipios.json` lê do arquivo versionado. É o modo de teste e de
  execução offline: determinístico, sem rede.
- `--fetch` baixa da API e grava o cache. É ato deliberado, não acontece sozinho.

**Nada de "5.570" no código.** O script conta o que veio e loga a contagem real. Fixar
o número faz o teste passar quando a fonte muda, que é o oposto de verificar.

Idempotente por `codigo_ibge`: rodar duas vezes não duplica e não perde `homologado`
nem credencial apontando para o município.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

URL_IBGE = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
CACHE_PADRAO = Path("data/ibge_municipios.json")


def normalizar(bruto: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Converte o formato do IBGE para o que o cadastro usa.

    O IBGE devolve `microrregiao.mesorregiao.UF.sigla` e `id` numérico; o cadastro usa
    `codigo_ibge` de 7 dígitos como texto e `uf` de 2 letras.
    """
    municipios: list[dict[str, Any]] = []
    for item in bruto:
        codigo = str(item.get("id", "")).zfill(7)
        uf = (item.get("microrregiao") or {}).get("mesorregiao", {}).get("UF", {}).get("sigla")
        # A API também expõe `regiao-imediata.regiao-intermediaria.UF`; o caminho acima
        # é o mais estável entre versões.
        if not uf:
            uf = (
                (item.get("regiao-imediata") or {})
                .get("regiao-intermediaria", {})
                .get("UF", {})
                .get("sigla")
            )
        nome = item.get("nome")
        if not codigo or not uf or not nome:
            continue
        municipios.append({"codigo_ibge": codigo, "nome": nome, "uf": uf})
    return municipios


def baixar(destino: Path = CACHE_PADRAO) -> list[dict[str, Any]]:
    """Baixa da API oficial e grava o cache. Ato explícito (`--fetch`)."""
    with urllib.request.urlopen(URL_IBGE, timeout=60) as resposta:
        bruto = json.loads(resposta.read().decode("utf-8"))
    municipios = normalizar(bruto)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(municipios, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    logger.info("cache gravado", extra={"total": len(municipios), "destino": str(destino)})
    return municipios


def carregar(caminho: Path = CACHE_PADRAO) -> list[dict[str, Any]]:
    if not caminho.is_file():
        raise FileNotFoundError(
            f"cache ausente: {caminho}. Rode com --fetch (rede) ou forneça o arquivo."
        )
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    if not isinstance(dados, list):
        raise ValueError("cache deve ser uma lista de municípios")
    return dados


async def aplicar(municipios: list[dict[str, Any]], *, dry_run: bool) -> dict[str, int]:
    """Upsert por `codigo_ibge`. Preserva `provedor`/`homologado` já definidos."""
    from app.db.models.municipio import MunicipioNFSe, ProvedorNFSe
    from app.db.session import obter_sessionmaker
    from sqlalchemy import select

    inseridos = atualizados = inalterados = 0
    async with obter_sessionmaker()() as sessao:
        for item in municipios:
            existente = (
                await sessao.execute(
                    select(MunicipioNFSe).where(MunicipioNFSe.codigo_ibge == item["codigo_ibge"])
                )
            ).scalar_one_or_none()

            if existente is None:
                inseridos += 1
                if not dry_run:
                    sessao.add(
                        MunicipioNFSe(
                            codigo_ibge=item["codigo_ibge"],
                            nome=item["nome"],
                            uf=item["uf"],
                            provedor=ProvedorNFSe.NACIONAL_REST,
                            # `fonte_url` é NOT NULL por R3: a origem fica registrada na
                            # linha, não só no script.
                            fonte_url=URL_IBGE,
                        )
                    )
            elif existente.nome != item["nome"] or existente.uf != item["uf"]:
                atualizados += 1
                if not dry_run:
                    existente.nome = item["nome"]
                    existente.uf = item["uf"]
            else:
                inalterados += 1
        if not dry_run:
            await sessao.commit()

    return {"inseridos": inseridos, "atualizados": atualizados, "inalterados": inalterados}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Popula municipios_nfse a partir do IBGE.")
    parser.add_argument("--fetch", action="store_true", help="baixa da API oficial do IBGE")
    parser.add_argument("--cache", type=Path, default=CACHE_PADRAO)
    parser.add_argument("--dry-run", action="store_true", help="mostra o diff sem gravar")
    args = parser.parse_args(argv)

    try:
        municipios = baixar(args.cache) if args.fetch else carregar(args.cache)
    except (FileNotFoundError, ValueError) as exc:
        print(f"erro: {exc}")
        return 2

    # Contagem real, não constante: o número vem do arquivo.
    print(f"municípios na fonte: {len(municipios)}")
    resultado = asyncio.run(aplicar(municipios, dry_run=args.dry_run))
    rotulo = "(dry-run, nada gravado)" if args.dry_run else ""
    print(
        f"inseridos: {resultado['inseridos']} | atualizados: {resultado['atualizados']} "
        f"| inalterados: {resultado['inalterados']} {rotulo}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
