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
MAPA = {
    "nfeautorizacao_4.00": "NFeAutorizacao",
    "nferetautorizacao_4.00": "NFeRetAutorizacao",
    "nfestatusservico_4.00": "NFeStatusServico",
    "nfeconsultaprotocolo_4.00": "NFeConsultaProtocolo",
    "nfeinutilizacao_4.00": "NFeInutilizacao",
    "recepcacevento_4.00": "NFeRecepcaoEvento",
    "recepaoevento_4.00": "NFeRecepcaoEvento",
}


def ler_secoes() -> dict[str, dict[str, str]]:
    texto = INI.read_text(encoding="latin-1")
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

    secoes = ler_secoes()
    linhas: list[dict] = []
    usados: Counter = Counter()

    # O mesmo INI cobre NF-e (`NFe_`) e NFC-e (`NFCe_`). O modelo vai na linha porque os
    # hosts divergem em algumas UFs (SP: nfe.fazenda.sp x nfce.fazenda.sp).
    for prefixo, modelo in (("NFe", "55"), ("NFCe", "65")):
        for uf in UFS:
            for sufixo, ambiente in (("P", "1"), ("H", "2")):
                secao, bloco = resolver(secoes, f"{prefixo}_{uf}_{sufixo}")
                if not bloco:
                    continue
                autorizador = secao.split("_")[1] if "_" in secao else uf
                usados[autorizador] += 1
                for chave, servico in MAPA.items():
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
                            "fonte_url": FONTE,
                            "autorizador": autorizador,
                        }
                    )

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
