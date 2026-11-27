"""Registra no manifesto as fontes oficiais coletadas em 2026-11-27 (segunda rodada).

Uso único, versionado por transparência: o manifesto é o registro, este script apenas evita erro de
transcrição de hash. Rodar de novo é idempotente — entradas já presentes são ignoradas.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

BASE = Path("sources/oficiais")
MANIFESTO = Path("sources/manifest.yaml")

NOVOS: list[dict[str, str]] = [
    {
        "id": "F-XSD-NT009-20261124",
        "requisito": "[REQ-1, REQ-2]",
        "titulo": "Esquemas XSD Produção Restrita 2026-11-24 (NT-009)",
        "url_arquivo": (
            "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/producao-restrita/"
            "esquemas-xsd-producao-restrita-20261124.zip"
        ),
        "arquivo": "esquemas-xsd-producao-restrita-20261124.zip",
        "limitacao": (
            "pacote oficial de 10 XSD; declara finNFSe, indDest, vAjusteBC, condominios, gCobranca, "
            "gDetCobranca e unidades — é o pacote que o Adendo 3 exigia"
        ),
    },
    {
        "id": "F-ANEXO-I-DPS-20261124",
        "requisito": "[REQ-1, REQ-2]",
        "titulo": "Anexo I SEFIN ADN DPS NFSe SNNFSe Produção Restrita v1.01 2026-11-24",
        "url_arquivo": (
            "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/producao-restrita/"
            "anexo_i-sefin_adn-dps_nfse-snnfse_prodrest-v1-01-20261124.xlsx"
        ),
        "arquivo": "anexo-i-dps-nfse-prodrest-v1.01-20261124.xlsx",
        "limitacao": "leiaute da DPS com os grupos da NT-009 (campo a campo)",
    },
    {
        "id": "F-NT-009-V1.01",
        "requisito": "[REQ-1, REQ-2]",
        "titulo": "Nota Técnica SE/CGNFS-e nº 009 versão 1.01 (01/10/2026)",
        "url_arquivo": (
            "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/"
            "nota-tecnica-009-se-cgnfs-e-v-1-01.pdf"
        ),
        "arquivo": "nt-009-se-cgnfs-e-v1.01-20261001.pdf",
        "limitacao": (
            "define finNFSe, vAjusteBC e os grupos de condomínio (subitem 99.05: vCobranca, vDescCond, "
            "grupo imovel)"
        ),
    },
    {
        "id": "F-ANEXO-VIII-1.02.00",
        "requisito": "[REQ-3]",
        "titulo": (
            "Anexo VIII versão 1.02.00 (26/10/2026) — correlação Item de Serv., NBS, cClassTrib e cIndOp"
        ),
        "url_arquivo": (
            "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/"
            "anexo_viii-tabela-correlacao-v01-02-00-20261026.xlsx"
        ),
        "arquivo": "anexo-viii-v01.02.00-20261026.xlsx",
        "limitacao": (
            "a própria página oficial traz AVISO: anexo em desenvolvimento e SEM regras de negócio "
            "baseadas nele no Piloto RTC nem em Produção"
        ),
    },
    {
        "id": "F-ANEXO-VI-RN-1.04.01",
        "requisito": "[REQ-1, REQ-2]",
        "titulo": "Anexo VI — Leiautes e Regras de Negócio RTC IBS/CBS v1.04.01 (NT-009)",
        "url_arquivo": (
            "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/"
            "anexovi-leiautesrn_rtc_ibscbs-v1-04-01-nt009.xlsx"
        ),
        "arquivo": "anexo-vi-leiautes-rn-rtc-ibscbs-v1.04.01-nt009.xlsx",
        "limitacao": "regras de negócio dos grupos IBS/CBS e de condomínios",
    },
    {
        "id": "F-ANEXO-VII-INDOp-1.03.00",
        "requisito": "[REQ-3]",
        "titulo": "Anexo VII — IndOp IBS/CBS v1.03.00 (NT-009)",
        "url_arquivo": (
            "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/"
            "anexovii-indop_ibscbs_v1-03-00-nt009.xlsx"
        ),
        "arquivo": "anexo-vii-indop-ibscbs-v1.03.00-nt009.xlsx",
        "limitacao": "tabela de indicador de operação (cIndOp)",
    },
    {
        "id": "F-ANEXO-B-NBS2",
        "requisito": "[REQ-3]",
        "titulo": "Anexo B — NBS 2.0 lista de serviço nacional v1.01 2026-01-22",
        "url_arquivo": (
            "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/producao-restrita/"
            "anexo_b-nbs2-lista_servico_nacional-snnfse-prodrest-v1-01-20260122.xlsx"
        ),
        "arquivo": "anexo-b-nbs2-v1.01-20260122.xlsx",
        "limitacao": "contém o código NBS 110019000",
    },
    {
        "id": "F-ANEXO-C-INDOp",
        "requisito": "[REQ-3]",
        "titulo": "Anexo C — IndOp IBS/CBS v1.01 2026-01-22",
        "url_arquivo": (
            "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/producao-restrita/"
            "anexo_c-indop_ibscbs-snnfse-prodrest-v1-01-20260122.xlsx"
        ),
        "arquivo": "anexo-c-indop-ibscbs-v1.01-20260122.xlsx",
        "limitacao": "contém o código 020201",
    },
]


def main() -> int:
    texto = MANIFESTO.read_text(encoding="utf-8")
    marcador = "\nnao_encontrado:\n"
    if marcador not in texto:
        raise SystemExit("marcador 'nao_encontrado:' não encontrado no manifesto")

    blocos: list[str] = []
    for item in NOVOS:
        caminho = BASE / item["arquivo"]
        if not caminho.is_file():
            raise SystemExit(f"arquivo ausente: {caminho}")
        if f"id: {item['id']}" in texto:
            continue
        tamanho = caminho.stat().st_size
        digest = hashlib.sha256(caminho.read_bytes()).hexdigest()
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

    if not blocos:
        print("manifesto já contém todas as entradas")
        return 0

    novo_texto = texto.replace(marcador, "".join(blocos) + marcador, 1)
    dados = yaml.safe_load(novo_texto)
    MANIFESTO.write_text(novo_texto, encoding="utf-8")
    print(f"fontes no manifesto: {len(dados['fontes'])}")
    print("adicionadas:", [i["id"] for i in NOVOS])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
