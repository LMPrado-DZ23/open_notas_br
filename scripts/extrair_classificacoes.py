"""Extrai o catálogo de classificação tributária do IBS/CBS da calculadora oficial.

Fonte: `calculadora-rtc-regime-regular` (SERPRO/Receita Federal), arquivo
`flyway/sql/criacao/B0001__sistema_tributario_completo.sql`, tabela
`CLASSIFICACAO_TRIBUTARIA`.

Por que um script e não dados digitados à mão: o catálogo tem centenas de linhas e
muda por migração da calculadora. Com o script, atualizar é rodar de novo contra a
versão nova — e a procedência fica registrada.

O SQL oficial traz um comentário `-- CLTR_COLUNA` antes de cada valor, o que
permite mapear coluna por valor sem heurística frágil de posição.

Uso::

    python -m scripts.extrair_classificacoes <caminho-do-sql> <saida.json>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MARCA = "INSERT INTO CLASSIFICACAO_TRIBUTARIA"
RE_COLUNA = re.compile(r"--\s*(CLTR_[A-Z_]+)")

#: Colunas que interessam ao produto. As demais (memória de cálculo completa,
#: indicadores de monofasia) ficam de fora nesta versão para não inflar o arquivo.
COLUNAS = (
    "CLTR_ID",
    "CLTR_CD",
    "CLTR_DESCRICAO",
    "CLTR_TIPO_ALIQUOTA",
    "CLTR_NOMENCLATURA",
    "CLTR_SITR_ID",
    "CLTR_INICIO_VIGENCIA",
    "CLTR_FIM_VIGENCIA",
    "CLTR_ANEXO",
)


def _limpar(valor: str) -> str:
    """Normaliza um valor SQL: corta o fechamento da linha, aspas e NULL.

    O último valor de cada tupla carrega o `\n)` que fecha o registro, e campos
    ausentes vêm como `NULL` literal. Sem esse corte, `fim_vigencia` virava
    `"NULL\n)"` e a checagem de vigência passava a mentir.
    """
    texto = valor.split("\n)")[0].strip()
    texto = texto.rstrip(",").strip()
    if texto.upper() == "NULL":
        return ""
    if texto.startswith("'") and texto.endswith("'"):
        texto = texto[1:-1]
    return texto.replace("''", "'").strip()


def extrair(sql: str) -> list[dict[str, str]]:
    """Devolve a lista de classificações encontradas no SQL."""
    inicio = sql.find(MARCA)
    if inicio == -1:
        raise SystemExit(f"marca não encontrada no SQL: {MARCA}")
    corpo = sql[inicio:]
    corpo = corpo[corpo.find("VALUES") + len("VALUES") :]

    # Cada linha de dados começa com "(" em uma linha própria.
    registros: list[dict[str, str]] = []
    for bruto in re.split(r"\n\s*\(\s*\n", corpo):
        if "CLTR_CD" not in bruto:
            continue
        # Quebra o bloco nos marcadores de coluna e associa marcador -> valor.
        partes = RE_COLUNA.split(bruto)
        # partes = [lixo, COLUNA, valor, COLUNA, valor, ...]
        campos: dict[str, str] = {}
        for i in range(1, len(partes) - 1, 2):
            coluna = partes[i]
            valor = partes[i + 1]
            if coluna in COLUNAS:
                campos[coluna] = _limpar(valor)

        codigo = campos.get("CLTR_CD", "")
        if not re.fullmatch(r"\d{6}", codigo):
            continue
        registros.append(
            {
                "id": campos.get("CLTR_ID", ""),
                "codigo": codigo,
                "descricao": campos.get("CLTR_DESCRICAO", ""),
                "tipo_aliquota": campos.get("CLTR_TIPO_ALIQUOTA", ""),
                "nomenclatura": campos.get("CLTR_NOMENCLATURA", ""),
                "situacao_tributaria_id": campos.get("CLTR_SITR_ID", ""),
                "inicio_vigencia": campos.get("CLTR_INICIO_VIGENCIA", ""),
                "fim_vigencia": campos.get("CLTR_FIM_VIGENCIA", ""),
                "anexo": campos.get("CLTR_ANEXO", ""),
            }
        )

    # NÃO deduplicar por código: o catálogo oficial é versionado e REUSA códigos
    # entre versões (000001 existe com descrição diferente em 2026 e em 2027).
    # Deduplicar apagaria a versão vigente para uma competência e faria o sistema
    # validar a nota contra a classificação errada.
    return sorted(registros, key=lambda r: (r["codigo"], r["inicio_vigencia"]))


def principal(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    origem = Path(argv[1])
    destino = Path(argv[2])

    sql = origem.read_text(encoding="utf-8", errors="replace")
    registros = extrair(sql)
    if not registros:
        print("nenhuma classificação extraída: verifique a versão do SQL", file=sys.stderr)
        return 1

    conteudo = {
        "fonte": "calculadora-rtc-regime-regular — CLASSIFICACAO_TRIBUTARIA",
        "gerado_por": "scripts/extrair_classificacoes.py",
        "aviso": (
            "Dados de referência oficial, extraídos do SQL da calculadora publicada "
            "pela Receita/SERPRO. Alterações na calculadora exigem reexecutar o script."
        ),
        "total": len(registros),
        "codigos_distintos": len({r["codigo"] for r in registros}),
        "classificacoes": registros,
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(conteudo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(registros)} classificações -> {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal(sys.argv))
