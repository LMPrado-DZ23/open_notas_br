"""Baixa fontes públicas de endpoints e registra procedência (URL, SHA-256, data).

Por que um script e não arquivos colados à mão: endpoint de SEFAZ muda por portaria. Baixar
com hash e data permite provar **de onde** veio cada URL e **quando**, e refazer depois.

Fontes conhecidas nesta data:

- `wsnfe_4.00_mod55.xml` — repositório oficial da biblioteca NFePHP (sped-nfe), mantido pela
  comunidade e usado em produção por integradores. Cobre NF-e modelo 55: 15 autorizadores
  (AM, AN, BA, GO, MG, MS, MT, PE, PR, RS, SP, SVAN, SVRS, SVCAN, SVCRS).
- `wsnfe_4.00_mod65.xml` — o mesmo para NFC-e modelo 65 (matriz por UF).

Uso:
    python -m scripts.baixar_fontes
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

DESTINO = Path("data/fontes")
MANIFESTO = DESTINO / "MANIFESTO.json"

FONTES = {
    "wsnfe_4.00_mod55.xml": (
        "https://raw.githubusercontent.com/nfephp-org/sped-nfe/master/storage/wsnfe_4.00_mod55.xml"
    ),
    "wsnfe_4.00_mod65.xml": (
        "https://raw.githubusercontent.com/nfephp-org/sped-nfe/master/storage/wsnfe_4.00_mod65.xml"
    ),
}


def baixar() -> int:
    DESTINO.mkdir(parents=True, exist_ok=True)
    registro: dict[str, dict[str, str]] = {}
    falhas: list[str] = []

    with httpx.Client(timeout=30.0, follow_redirects=True) as cliente:
        for nome, url in FONTES.items():
            print(f"[..] {nome}")
            try:
                resposta = cliente.get(url)
                resposta.raise_for_status()
            except httpx.HTTPError as exc:
                print(f"[FALHOU] {nome}: {exc}")
                falhas.append(nome)
                continue

            conteudo = resposta.content
            (DESTINO / nome).write_bytes(conteudo)
            registro[nome] = {
                "url": url,
                "sha256": hashlib.sha256(conteudo).hexdigest(),
                "bytes": str(len(conteudo)),
                "baixado_em": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            print(f"[OK] {nome} ({len(conteudo)} bytes)")

    MANIFESTO.write_text(
        json.dumps(registro, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"manifesto: {MANIFESTO}")
    if falhas:
        print(f"{len(falhas)} fonte(s) falharam: {', '.join(falhas)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(baixar())
