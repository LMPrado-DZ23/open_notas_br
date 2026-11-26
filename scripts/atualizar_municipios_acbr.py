"""Atualiza municipios_nfse a partir do ACBrNFSeXServicos.ini.

O INI do ACBr tem 5.571 seções (uma por município do IBGE) com provedor, versão do leiaute e
URLs de produção/homologação. Ele é a fonte que faltava para as prefeituras.

Regras — e o motivo de cada uma:

- **Só `https://` entra.** 1.629 URLs do arquivo são `http://`: credencial e XML fiscal em
  texto claro não entram no banco, mesmo que o provedor aceite.
- **Provedor fora do enum é recusado e contado.** O enum do projeto tem 6 provedores reais;
  o INI tem 17+. Inventar valor de enum para caber seria pior que recusar com relatório.
- **`padraonacional` vira `nacional_rest`**: esses municípios não têm endpoint próprio, usam
  o endpoint único nacional.
- **A fonte fica gravada** (`fonte_url` = URL do INI no SVN do ACBr).

Uso:
    python -m scripts.atualizar_municipios_acbr            # dry-run
    python -m scripts.atualizar_municipios_acbr --aplicar
"""

from __future__ import annotations

import argparse
import asyncio
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.db.models.municipio import MunicipioNFSe, ProvedorNFSe
from app.db.session import dispose_engine, obter_sessionmaker
from sqlalchemy import select

INI = Path("data/fontes/ACBrNFSeXServicos.ini")
FONTE = "https://svn.code.sf.net/p/acbr/code/trunk2/Fontes/ACBrDFe/ACBrNFSeX/ACBrNFSeXServicos.ini"
#: Nome no INI -> valor do nosso enum. Só o que existe dos dois lados.
ALIAS = {"padraonacional": "nacional_rest"}


@dataclass(frozen=True, slots=True)
class MunicipioINI:
    codigo_ibge: str
    nome: str
    uf: str
    provedor: str
    url_producao: str | None
    url_homologacao: str | None
    versao_layout: str | None


@dataclass
class Resumo:
    lidos: int = 0
    importaveis: int = 0
    sem_provedor: int = 0
    provedor_desconhecido: int = 0
    sem_url_https: int = 0
    atualizados: int = 0
    provedores_recusados: Counter = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.provedores_recusados is None:
            self.provedores_recusados = Counter()


def ler_ini(resumo: Resumo) -> list[MunicipioINI]:
    texto = INI.read_text(encoding="latin-1")
    validos = {m.value for m in ProvedorNFSe}
    saida: list[MunicipioINI] = []

    for achado in re.finditer(r"^\[(\d{7})\](.*?)(?=^\[|\Z)", texto, flags=re.M | re.S):
        resumo.lidos += 1
        codigo, corpo = achado.group(1), achado.group(2)
        kv: dict[str, str] = {}
        for linha in corpo.splitlines():
            if "=" in linha and not linha.strip().startswith(";"):
                chave, valor = linha.split("=", 1)
                kv[chave.strip()] = valor.strip()

        provedor = ALIAS.get(kv.get("Provedor", "").lower(), kv.get("Provedor", "").lower())
        if not provedor:
            resumo.sem_provedor += 1
            continue
        if provedor not in validos:
            resumo.provedor_desconhecido += 1
            resumo.provedores_recusados[provedor] += 1
            continue

        prod = kv.get("ProRecepcionar", "")
        hom = kv.get("HomRecepcionar", "")
        prod = prod if prod.startswith("https://") else None
        hom = hom if hom.startswith("https://") else None
        # `nacional_rest` não tem endpoint por município: usa o endpoint único nacional.
        # Recusar por falta de URL aqui confundiria "não tem URL própria" com "não tem
        # caminho de emissão".
        if prod is None and hom is None and provedor != "nacional_rest":
            resumo.sem_url_https += 1
            continue

        resumo.importaveis += 1
        saida.append(
            MunicipioINI(
                codigo_ibge=codigo,
                nome=kv.get("Nome", ""),
                uf=kv.get("UF", ""),
                provedor=provedor,
                url_producao=prod,
                url_homologacao=hom,
                versao_layout=kv.get("Versao") or None,
            )
        )
    return saida


async def executar(aplicar: bool) -> int:
    resumo = Resumo()
    dados = ler_ini(resumo)

    async with obter_sessionmaker()() as sessao:
        existentes = {
            m.codigo_ibge: m for m in (await sessao.execute(select(MunicipioNFSe))).scalars()
        }

        for item in dados:
            linha = existentes.get(item.codigo_ibge)
            if linha is None:
                continue
            linha.provedor = ProvedorNFSe(item.provedor)
            linha.url_producao = item.url_producao
            linha.url_homologacao = item.url_homologacao
            linha.versao_layout = item.versao_layout
            linha.fonte_url = FONTE
            resumo.atualizados += 1

        if aplicar:
            await sessao.commit()

    print(f"seções no INI            : {resumo.lidos}")
    print(f"importáveis (https)      : {resumo.importaveis}")
    print(f"sem provedor             : {resumo.sem_provedor}")
    print(f"provedor fora do enum    : {resumo.provedor_desconhecido}")
    print(f"sem URL https            : {resumo.sem_url_https}")
    print(f"atualizados no banco     : {resumo.atualizados}")
    if resumo.provedores_recusados:
        top = resumo.provedores_recusados.most_common(8)
        print(f"provedores mais recusados: {top}")
    print("aplicado" if aplicar else "dry-run: nada gravado (use --aplicar)")
    await dispose_engine()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true")
    args = parser.parse_args(argv)
    if not INI.is_file():
        print(f"arquivo ausente: {INI}")
        return 2
    return asyncio.run(executar(args.aplicar))


if __name__ == "__main__":
    raise SystemExit(main())
