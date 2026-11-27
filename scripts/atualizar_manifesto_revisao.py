"""Atualiza o manifesto com as fontes coletadas na revisão de continuidade (2026-11-27, 3ª rodada).

Idempotente: entradas já presentes são ignoradas. Também corrige a entrada do Adendo 3, que estava
com caminho absoluto do disco do usuário e sem hash — dois defeitos para um manifesto versionado.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

MANIFESTO = Path("sources/manifest.yaml")

NOVOS: list[dict[str, str]] = [
    {
        "id": "F-COMUNICADO-RELEASE-2",
        "requisito": "[REQ-1, REQ-2, REQ-4]",
        "titulo": (
            "CGNFS-e informa: disponibilizado no ambiente de testes o Release 2 das evoluções da "
            "Nota Técnica 009 (publicado 25/11/2026, atualizado 27/11/2026)"
        ),
        "url_arquivo": (
            "https://www.gov.br/nfse/pt-br/noticias/"
            "cgnfs-e-informa-disponibilizado-no-ambiente-de-testes-o-release-2-das-evolucoes-da-"
            "nota-tecnica-009"
        ),
        "arquivo": "comunicado-release-2-20261125.html",
        "limitacao": (
            "cronograma oficial: Release 2 (NT-009 v1.01 itens 2.9-2.14) em Produção Restrita em "
            "24/11/2026 e produção em 07/12/2026; Release 3 (07/12/2026) traz o item 2.15 Operações "
            "Condominiais, ainda em desenvolvimento; procuração/alternância de perfis já em produção "
            "desde 31/10/2026"
        ),
    },
    {
        "id": "F-FAQ-NFSE-V1.5",
        "requisito": "[REQ-4]",
        "titulo": "Perguntas Frequentes da NFS-e — versão 1.5 (23/11/2026)",
        "url_arquivo": "https://www.gov.br/nfse/pt-br/perguntas-frequentes/teste-do-perguntas",
        "arquivo": "faq-nfse-v1.5-20261123.html",
        "limitacao": (
            "Tema 28: procuração eletrônica é concedida no Portal de Serviços da RFB para os serviços "
            "da NFS-e e o vínculo é validado na alternância de perfil; emitente segue sendo o "
            "outorgante. NÃO cita o código de serviço 00233 e NÃO documenta API de consulta de "
            "vigência/revogação"
        ),
    },
]

CORRECAO_ADENDO = {
    "arquivo": "sources/adendos/adendo-3-evidencias-oficiais-2026-11-27.md",
    "caminho_local": "sources/adendos/adendo-3-evidencias-oficiais-2026-11-27.md",
}


def _sha(caminho: Path) -> tuple[int, str]:
    return caminho.stat().st_size, hashlib.sha256(caminho.read_bytes()).hexdigest()


def main() -> int:
    texto = MANIFESTO.read_text(encoding="utf-8")
    dados = yaml.safe_load(texto)
    ids = {f["id"] for f in dados["fontes"]}

    blocos: list[str] = []
    for item in NOVOS:
        if item["id"] in ids:
            continue
        caminho = Path("sources/oficiais") / item["arquivo"]
        if not caminho.is_file():
            raise SystemExit(f"arquivo ausente: {caminho}")
        tamanho, digest = _sha(caminho)
        blocos.append(
            "\n"
            f"  - id: {item['id']}\n"
            f"    requisito: {item['requisito']}\n"
            "    orgao: cgnfs-e\n"
            f'    titulo: "{item["titulo"]}"\n'
            f'    url_arquivo: "{item["url_arquivo"]}"\n'
            f"    arquivo: sources/oficiais/{item['arquivo']}\n"
            f"    bytes: {tamanho}\n"
            f"    sha256: {digest}\n"
            '    data_acesso: "2026-11-27"\n'
            "    status_coleta: coletado\n"
            f'    limitacao: "{item["limitacao"]}"\n'
        )

    if blocos:
        marcador = "\nnao_encontrado:\n"
        texto = texto.replace(marcador, "".join(blocos) + marcador, 1)

    # Correção da entrada do Adendo 3: sair de caminho absoluto do disco do usuário e ganhar hash.
    alvo = "sources/adendos/adendo-3-evidencias-oficiais-2026-11-27.md"
    if "C:/Users/" in texto:
        arquivo_local = Path(alvo)
        tamanho, digest = _sha(arquivo_local)
        texto = texto.replace(
            '    arquivo: "C:/Users/lmpra/Downloads/'
            'adendo-3-deepseek-evidencias-oficiais-regras-fiscais-2026-11-27.md"\n',
            f"    arquivo: {alvo}\n    bytes: {tamanho}\n    sha256: {digest}\n",
        )

    dados = yaml.safe_load(texto)
    MANIFESTO.write_text(texto, encoding="utf-8")
    print(f"fontes no manifesto: {len(dados['fontes'])}")
    print("caminho absoluto remanescente:", "C:/Users/" in texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
