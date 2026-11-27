"""Gera a coleção Postman a partir do `openapi.json` versionado.

Por que gerar em vez de escrever à mão: coleção manual divergiu do contrato em todo projeto que
cresceu. Aqui a fonte é o próprio contrato, e `--check` reprova quando o arquivo commitado não
corresponde — então a coleção não pode envelhecer em silêncio.

Os corpos são **esqueletos derivados do schema** (string vazia, zero, lista vazia), não exemplos de
negócio: inventar CNPJ, valor ou município "de exemplo" produziria coleção que parece pronta e
falha no primeiro uso. Onde há `examples` no schema, eles são usados.

Uso:

    python -m scripts.gerar_postman            # grava docs/postman_collection.json
    python -m scripts.gerar_postman --check    # compara sem gravar (sai 1 se divergir)
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
OPENAPI = RAIZ / "openapi.json"
DESTINO = RAIZ / "docs" / "postman_collection.json"

#: Valor de exemplo por tipo JSON Schema. Deliberadamente vazio/neutro: ver docstring do módulo.
_POR_TIPO: dict[str, Any] = {
    "string": "",
    "integer": 0,
    "number": 0,
    "boolean": False,
    "array": [],
    "object": {},
}


def _esqueleto(schema: dict[str, Any], *, profundidade: int = 0) -> Any:
    """Corpo mínimo que satisfaz a forma do schema. Não inventa dado de negócio."""
    if profundidade > 4:
        return {}

    if "example" in schema:
        return schema["example"]
    if schema.get("examples"):
        return schema["examples"][0]
    if "default" in schema:
        return schema["default"]

    for chave in ("allOf", "anyOf", "oneOf"):
        if schema.get(chave):
            return _esqueleto(schema[chave][0], profundidade=profundidade + 1)

    if "$ref" in schema:
        # Referência não resolvida aqui de propósito: quem chama resolve antes (ver `_resolver`).
        return {}

    tipo = schema.get("type")
    if tipo == "object" or "properties" in schema:
        return {
            nome: _esqueleto(prop, profundidade=profundidade + 1)
            for nome, prop in (schema.get("properties") or {}).items()
        }
    if tipo == "array":
        item = schema.get("items") or {}
        return [_esqueleto(item, profundidade=profundidade + 1)]
    return _POR_TIPO.get(tipo, "")


def _resolver(schema: dict[str, Any], componentes: dict[str, Any]) -> dict[str, Any]:
    """Resolve `$ref` de primeiro nível (os schemas deste projeto não são cíclicos)."""
    if "$ref" not in schema:
        return schema
    nome = schema["$ref"].rsplit("/", 1)[-1]
    return componentes.get(nome, {})


def _cabecalhos() -> list[dict[str, Any]]:
    return [
        {
            "key": "X-API-Key",
            "value": "{{api_key}}",
            "description": "Chave do tenant. Deriva o tenant — nunca envie tenant_id no corpo.",
        },
        {"key": "Content-Type", "value": "application/json"},
    ]


def _requisicao(
    metodo: str,
    caminho: str,
    operacao: dict[str, Any],
    componentes: dict[str, Any],
) -> dict[str, Any]:
    caminho_postman = "{{base_url}}" + caminho
    itens: dict[str, Any] = {
        "name": operacao.get("summary") or f"{metodo.upper()} {caminho}",
        "request": {
            "method": metodo.upper(),
            "header": _cabecalhos(),
            "url": {
                "raw": caminho_postman,
                "host": ["{{base_url}}"],
                "path": [parte for parte in caminho.split("/") if parte],
            },
            "description": (operacao.get("description") or "").strip(),
        },
    }

    corpo = (operacao.get("requestBody") or {}).get("content", {}).get("application/json")
    if corpo:
        schema = _resolver(corpo.get("schema") or {}, componentes)
        itens["request"]["body"] = {
            "mode": "raw",
            "raw": json.dumps(_esqueleto(schema), ensure_ascii=False, indent=2),
            "options": {"raw": {"language": "json"}},
        }
    return itens


def construir(openapi: dict[str, Any]) -> dict[str, Any]:
    componentes = (openapi.get("components") or {}).get("schemas") or {}
    pastas: dict[str, list[dict[str, Any]]] = {}

    for caminho, operacoes in sorted((openapi.get("paths") or {}).items()):
        for metodo, operacao in operacoes.items():
            if metodo.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            etiquetas = operacao.get("tags") or ["outros"]
            pasta = etiquetas[0]
            pastas.setdefault(pasta, []).append(_requisicao(metodo, caminho, operacao, componentes))

    return {
        "info": {
            "_postman_id": str(uuid.uuid5(uuid.NAMESPACE_URL, "open-notas-br/collection")),
            "name": "open_notas_br",
            "description": (
                "Coleção gerada por `python -m scripts.gerar_postman` a partir de `openapi.json`.\n"
                "Não edite à mão: `--check` reprova quando diverge do contrato.\n"
                "Os corpos são esqueletos derivados do schema (string vazia, zero) — preencha com "
                "dado real. Variáveis: `base_url` e `api_key`."
            ),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [
            {"key": "base_url", "value": "http://127.0.0.1:8081"},
            {"key": "api_key", "value": ""},
        ],
        "item": [{"name": pasta, "item": itens} for pasta, itens in sorted(pastas.items())],
    }


def gerar() -> str:
    openapi = json.loads(OPENAPI.read_text(encoding="utf-8"))
    return json.dumps(construir(openapi), ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    conteudo = gerar()

    if "--check" in argv:
        atual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        if atual != conteudo:
            print(
                f"{DESTINO.relative_to(RAIZ)} diverge do contrato. "
                "Rode: python -m scripts.gerar_postman",
                file=sys.stderr,
            )
            return 1
        print(f"{DESTINO.relative_to(RAIZ)} em dia com o contrato")
        return 0

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(conteudo, encoding="utf-8")
    print(f"colecao gravada em {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
