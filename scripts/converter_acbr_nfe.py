"""Resolve UF -> autorizador -> URL 4.00 a partir do ACBrNFeServicos.ini.

O arquivo tem uma indireção explícita: o bloco da UF pode dizer `Usar=NFe_SVRS_P`. Seguir
essa cadeia é usar o dado da própria fonte — diferente de deduzir "AC fica com SVRS" por
semelhança.

Duas armadilhas tratadas aqui:

- **`?wsdl` não é endpoint.** Muitas linhas trazem a URL do WSDL. Enviar SOAP para o WSDL
  devolve erro de contrato, não de dados. O sufixo é removido e o endpoint fica correto.
- **Chave do serviço é case-insensitive na prática** (`NFeAutorizacao_4.00` e
  `NfeAutorizacao_4.00` coexistem). Normalizar para minúsculas antes de procurar — comparar
  case-sensitive achou só 10 das 27 UFs.

Uso:
    python -m scripts.converter_acbr_nfe            # gera data/endpoints_nfe_acbr.json
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from app.catalogo import UFS, validar_lote

INI = Path("data/fontes/ACBrNFeServicos.ini")
FONTE = "https://svn.code.sf.net/p/acbr/code/trunk2/Fontes/ACBrDFe/ACBrNFe/ACBrNFeServicos.ini"
SAIDA = Path("data/endpoints_nfe_acbr.json")

#: Chave no INI (minúscula) -> serviço do nosso enum.
FONTE_CTE = "https://svn.code.sf.net/p/acbr/code/trunk2/Fontes/ACBrDFe/ACBrCTe/ACBrCTeServicos.ini"
FONTE_MDFE = (
    "https://svn.code.sf.net/p/acbr/code/trunk2/Fontes/ACBrDFe/ACBrMDFe/ACBrMDFeServicos.ini"
)

MAPA_CTE = {
    "cterecepcaosinc_3.00": "CTeRecepcaoSinc",
    "cterecepcaosinc_4.00": "CTeRecepcaoSinc",
    "cterecepcaoevento_3.00": "CTeRecepcaoEvento",
    "cterecepcaoevento_4.00": "CTeRecepcaoEvento",
    # O INI do ACBr grafa a chave do evento SEM o prefixo do documento nas seções
    # compartilhadas (`RecepcaoEvento_3.00`). Sem estas linhas, só a recepção síncrona
    # entrava no catálogo e o CT-e ficava com 1 de 7 serviços (auditoria §30).
    "recepcaoevento_3.00": "CTeRecepcaoEvento",
    "recepcaoevento_4.00": "CTeRecepcaoEvento",
    "ctestatusservico_3.00": "CTeStatusServico",
    "ctestatusservico_4.00": "CTeStatusServico",
    "cteretrecepcao_3.00": "CTeRetRecepcao",
}
MAPA_MDFE = {
    "mdferecepcaosinc_3.00": "MDFeRecepcaoSinc",
    "mdferecepcaoevento_3.00": "MDFeRecepcaoEvento",
    # Mesma indireção do CT-e: a chave do evento aparece sem o prefixo do documento.
    "recepcaoevento_1.00": "MDFeRecepcaoEvento",
    "recepcaoevento_3.00": "MDFeRecepcaoEvento",
    "mdfestatusservico_1.00": "MDFeStatusServico",
    "mdfestatusservico_3.00": "MDFeStatusServico",
    "mdferetrecepcao_1.00": "MDFeRetRecepcao",
}

MAPA = {
    "nfeautorizacao_4.00": "NFeAutorizacao",
    "nferetautorizacao_4.00": "NFeRetAutorizacao",
    "nfestatusservico_4.00": "NFeStatusServico",
    "nfeconsultaprotocolo_4.00": "NFeConsultaProtocolo",
    "nfeinutilizacao_4.00": "NFeInutilizacao",
    "recepcacevento_4.00": "NFeRecepcaoEvento",
    "recepaoevento_4.00": "NFeRecepcaoEvento",
}


def ler_secoes(caminho: Path | None = None) -> dict[str, dict[str, str]]:
    texto = (caminho or INI).read_text(encoding="latin-1")
    secoes: dict[str, dict[str, str]] = {}
    for achado in re.finditer(r"^\[([^\]]+)\](.*?)(?=^\[|\Z)", texto, flags=re.M | re.S):
        nome, corpo = achado.group(1).strip(), achado.group(2)
        kv: dict[str, str] = {}
        for linha in corpo.splitlines():
            if "=" in linha and not linha.strip().startswith(";"):
                chave, valor = linha.split("=", 1)
                kv[chave.strip().lower()] = valor.strip()
        secoes[nome] = kv
    return secoes


def resolver(secoes: dict[str, dict[str, str]], inicial: str) -> tuple[str, dict[str, str]]:
    """Segue a cadeia `Usar=` até um bloco com chaves de serviço."""
    atual = inicial
    for _ in range(4):
        bloco = secoes.get(atual)
        if bloco is None:
            return atual, {}
        if any(k in bloco for k in MAPA):
            return atual, bloco
        proximo = bloco.get("usar")
        if not proximo:
            return atual, bloco
        atual = proximo
    return atual, secoes.get(atual, {})


def limpar(url: str) -> str:
    """Remove `?wsdl`: o endpoint SOAP é a URL sem o sufixo de descrição."""
    return url.split("?")[0].strip()


def main() -> int:
    if not INI.is_file():
        print(f"arquivo ausente: {INI} (baixe de {FONTE})")
        return 2

    linhas: list[dict] = []
    usados: Counter = Counter()

    # Um INI por documento, mesma estrutura e mesma indireção `Usar=`.
    # O modelo vai na linha porque os hosts divergem em algumas UFs
    # (SP: nfe.fazenda.sp x nfce.fazenda.sp).
    FONTES_POR_DOC = (
        (INI, "NFe", "55", MAPA, FONTE),
        (INI, "NFCe", "65", MAPA, FONTE),
        (Path("data/fontes/ACBrCTeServicos.ini"), "CTe", "57", MAPA_CTE, FONTE_CTE),
        (Path("data/fontes/ACBrMDFeServicos.ini"), "MDFe", "58", MAPA_MDFE, FONTE_MDFE),
    )

    for arquivo, prefixo, modelo, mapa, fonte in FONTES_POR_DOC:
        if not arquivo.is_file():
            print(f"aviso: {arquivo} ausente — pulando {prefixo}")
            continue
        secoes = ler_secoes(arquivo)
        for uf in UFS:
            for sufixo, ambiente in (("P", "1"), ("H", "2")):
                secao, bloco = resolver(secoes, f"{prefixo}_{uf}_{sufixo}")
                if not bloco:
                    continue
                autorizador = secao.split("_")[1] if "_" in secao else uf
                usados[autorizador] += 1
                for chave, servico in mapa.items():
                    url = bloco.get(chave)
                    if not url:
                        continue
                    limpa = limpar(url)
                    if not limpa.startswith("https://"):
                        continue
                    linhas.append(
                        {
                            "uf": uf,
                            "modelo": modelo,
                            "ambiente": ambiente,
                            "servico": servico,
                            "url": limpa,
                            "versao_soap": "1.2",
                            "fonte_url": fonte,
                            "autorizador": autorizador,
                        }
                    )

    # O mesmo serviço aparece em duas versões (3.00 e 4.00) e ambas caem no mesmo nome do
    # nosso enum. Ficar com as duas gera chave `(uf, modelo, ambiente, servico)` repetida.
    # Preferir a **última** ocorrência: os blocos 4.00 vêm depois dos 3.00 no arquivo.
    unicas: dict[tuple[str, str, str, str], dict] = {}
    for linha in linhas:
        unicas[(linha["uf"], linha["modelo"], linha["ambiente"], linha["servico"])] = linha
    if len(unicas) != len(linhas):
        print(f"deduplicado: {len(linhas)} -> {len(unicas)} (versões 3.00/4.00 do mesmo serviço)")
    linhas = list(unicas.values())

    validas, erros = validar_lote(linhas)
    for erro in erros[:5]:
        print(f"  ERRO: {erro}")

    SAIDA.write_text(json.dumps(linhas, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ufs_com = len({linha["uf"] for linha in linhas})
    print(f"linhas={len(linhas)} válidas={len(validas)} erros={len(erros)} UFs={ufs_com}/27")
    print(f"autorizadores usados: {usados.most_common(6)}")
    print(f"-> {SAIDA}")
    return 1 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
