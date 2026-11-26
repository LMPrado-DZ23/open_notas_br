"""Converte os XML versionados de endpoints em JSON para o importador.

Lê `data/fontes/wsnfe_4.00_mod55.xml` e `wsnfe_4.00_mod65.xml` (baixados por
`scripts.baixar_fontes`, com hash no MANIFESTO) e produz o JSON que
`scripts.importar_catalogo` consome.

Regras, e o motivo de cada uma:

- **`fonte_url`** é a URL bruta do arquivo no GitHub: é a prova de onde a URL saiu.
- **Sigla que não é UF é descartada com aviso.** `SVRS`, `SVAN`, `SVCAN`, `SVCRS` e `AN` são
  autorizadores; gravar `uf="SVRS"` criaria linha que tenant nenhum consulta.
- **`autorizador`** é a sigla do bloco — o virtual entra aí, que é o campo certo.
- Elemento sem URL não vira linha: `NfeConsultaCadastro` vazio em vários autorizadores.

Uso:
    python -m scripts.converter_wsurls            # gera data/endpoints_sefaz.json
"""

from __future__ import annotations

import json
from pathlib import Path

from app.catalogo import UFS, validar_lote
from lxml import etree

FONTES = Path("data/fontes")
SAIDA = Path("data/endpoints_sefaz.json")

#: Elemento do XML -> serviço do nosso enum. Só o que existe dos dois lados.
MAPA_SERVICOS = {
    "NfeStatusServico": "NFeStatusServico",
    "NfeAutorizacao": "NFeAutorizacao",
    "NfeRetAutorizacao": "NFeRetAutorizacao",
    "NfeConsultaProtocolo": "NFeConsultaProtocolo",
    "NfeRecepcaoEvento": "NFeRecepcaoEvento",
    "NfeInutilizacao": "NFeInutilizacao",
    "NfeDistribuicaoDFe": "NFeDistribuicaoDFe",
}


def _texto(elemento) -> str:
    return (elemento.text or "").strip()


def converter(arquivo: str, modelo: str) -> tuple[list[dict], list[str]]:
    caminho = FONTES / arquivo
    if not caminho.is_file():
        return [], [f"arquivo ausente: {caminho} (rode scripts.baixar_fontes)"]

    raiz = etree.parse(str(caminho)).getroot()
    fonte = "https://raw.githubusercontent.com/nfephp-org/sped-nfe/master/storage/" + arquivo
    linhas: list[dict] = []
    avisos: list[str] = []

    for bloco in raiz.findall(".//UF"):
        sigla = _texto(bloco.find("sigla"))
        if sigla not in UFS:
            avisos.append(f"{arquivo}: {sigla} é autorizador, não UF — descartado")
            continue

        for ambiente, tag in (("2", "homologacao"), ("1", "producao")):
            secao = bloco.find(tag)
            if secao is None:
                continue
            for elemento in secao:
                servico = MAPA_SERVICOS.get(etree.QName(elemento).localname)
                if servico is None:
                    continue
                url = _texto(elemento)
                if not url:
                    continue
                linhas.append(
                    {
                        "uf": sigla,
                        "modelo": modelo,
                        "ambiente": ambiente,
                        "servico": servico,
                        "url": url,
                        "versao_soap": "1.2",
                        "fonte_url": fonte,
                        "autorizador": sigla,
                    }
                )
    return linhas, avisos


def main() -> int:
    todas: list[dict] = []
    avisos: list[str] = []

    for arquivo, modelo in (
        ("wsnfe_4.00_mod55.xml", "55"),
        ("wsnfe_4.00_mod65.xml", "65"),
    ):
        linhas, avisos_arq = converter(arquivo, modelo)
        avisos.extend(avisos_arq)
        print(f"{arquivo}: {len(linhas)} endpoint(s)")
        todas.extend(linhas)

    for aviso in avisos:
        print(f"  aviso: {aviso}")

    # Valida antes de gravar: se algo aqui não passar, o importador recusaria depois.
    validas, erros = validar_lote(todas)
    for erro in erros:
        print(f"  ERRO: {erro}")

    SAIDA.write_text(json.dumps(todas, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"total={len(todas)} válidas={len(validas)} erros={len(erros)} -> {SAIDA}")
    return 1 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
