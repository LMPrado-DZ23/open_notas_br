"""Relatório de cobertura fiscal: quanto do território está realmente configurado.

Mede no banco. Não estima, não projeta: mostra o que existe hoje.

    python -m scripts.cobertura_fiscal
"""

from __future__ import annotations

import asyncio
import sys

from app.catalogo import UFS, medir_cobertura
from app.db.models.municipio import MunicipioNFSe
from app.db.session import dispose_engine, obter_sessionmaker
from sqlalchemy import func, select


async def executar() -> int:
    async with obter_sessionmaker()() as sessao:
        print("== NFS-e nacional (municípios) ==")
        total = (await sessao.execute(select(func.count()).select_from(MunicipioNFSe))).scalar_one()
        com_url = (
            await sessao.execute(
                select(func.count())
                .select_from(MunicipioNFSe)
                .where(MunicipioNFSe.url_producao.is_not(None))
            )
        ).scalar_one()
        com_fonte = (
            await sessao.execute(
                select(func.count())
                .select_from(MunicipioNFSe)
                .where(MunicipioNFSe.fonte_url.is_not(None))
            )
        ).scalar_one()
        homologados = (
            await sessao.execute(
                select(func.count())
                .select_from(MunicipioNFSe)
                .where(MunicipioNFSe.homologado.is_(True))
            )
        ).scalar_one()
        print(f"municípios cadastrados : {total}")
        print(f"com URL de produção    : {com_url}")
        print(f"com fonte registrada   : {com_fonte}")
        print(f"homologados (testados) : {homologados}")

        for modelo, nome_modelo in (("55", "NF-e"), ("65", "NFC-e")):
            for ambiente, rotulo in (("2", "homologação"), ("1", "produção")):
                cobertura = await medir_cobertura(sessao, ambiente=ambiente, modelo=modelo)
                print(f"\n== SEFAZ {nome_modelo} ({rotulo}) ==")
                print(
                    f"UFs com autorização cadastrada: "
                    f"{len(cobertura.ufs_com_autorizacao)}/{len(UFS)} "
                    f"({cobertura.percentual:.1f}%)"
                )
                if cobertura.ufs_sem_autorizacao:
                    print(f"sem cadastro: {' '.join(cobertura.ufs_sem_autorizacao)}")

        print(
            "\nEste número é o que existe. Zero significa que nenhum endpoint de SEFAZ "
            "foi cadastrado — não que o código não suporte."
        )
    await dispose_engine()
    return 0


def main() -> int:
    return asyncio.run(executar())


if __name__ == "__main__":
    sys.exit(main())
