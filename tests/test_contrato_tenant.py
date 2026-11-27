"""Trava da regra 7: o cliente **não** escolhe o tenant pelo corpo nem pela query (§68).

O tenant vem da credencial (`X-API-Key`). Se algum schema de entrada passar a aceitar `tenant_id`,
quem enviar o id de outro tenant pode tentar ler ou escrever dado alheio — e um `where` mal escrito
fecha o vazamento. Este teste existe para que a regressão apareça no CI, e não em auditoria.

Exceção deliberada e documentada: as rotas `/v1/admin/...` recebem `tenant_id` **explícito**, porque
operação de plataforma atravessa tenants por natureza (ADR 0001). Deixar implícito esconderia qual
tenant está sendo afetado — o oposto de segurança. A exceção é por **prefixo de rota**, não por
"ignorar admin no teste".
"""

from __future__ import annotations

import json

import pytest
from scripts.gerar_postman import RAIZ

#: Prefixo onde `tenant_id` explícito é aceitável (operação de plataforma autenticada por admin).
PREFIXO_ADMIN = "/v1/admin"


@pytest.fixture(scope="module")
def contrato() -> dict:
    return json.loads((RAIZ / "openapi.json").read_text(encoding="utf-8"))


def _resolver(schema: dict, componentes: dict) -> dict:
    if "$ref" in schema:
        return componentes.get(schema["$ref"].rsplit("/", 1)[-1], {})
    return schema


def _properties(schema: dict, componentes: dict) -> set[str]:
    """Nomes de propriedade no primeiro nível, resolvendo `$ref`."""
    resolvido = _resolver(schema, componentes)
    for chave in ("allOf", "anyOf", "oneOf"):
        if chave in resolvido:
            nomes: set[str] = set()
            for parte in resolvido[chave]:
                nomes |= _properties(parte, componentes)
            return nomes
    return set((resolvido.get("properties") or {}).keys())


class TestCorpo:
    def test_nenhum_request_body_aceita_tenant_id(self, contrato) -> None:
        componentes = contrato["components"]["schemas"]
        violacoes: list[str] = []

        for caminho, operacoes in contrato["paths"].items():
            if caminho.startswith(PREFIXO_ADMIN):
                continue
            for metodo, operacao in operacoes.items():
                conteudo = (operacao.get("requestBody") or {}).get("content") or {}
                for tipo, corpo in conteudo.items():
                    schema = corpo.get("schema") or {}
                    if "tenant_id" in _properties(schema, componentes):
                        violacoes.append(f"{metodo.upper()} {caminho} ({tipo})")

        assert not violacoes, (
            "tenant_id aceito no corpo — o tenant deve vir da credencial: " + ", ".join(violacoes)
        )


class TestQueryString:
    def test_nenhuma_rota_comum_aceita_tenant_id_na_query(self, contrato) -> None:
        violacoes: list[str] = []

        for caminho, operacoes in contrato["paths"].items():
            if caminho.startswith(PREFIXO_ADMIN):
                continue
            for metodo, operacao in operacoes.items():
                for parametro in operacao.get("parameters") or []:
                    if parametro.get("name") == "tenant_id" and parametro.get("in") == "query":
                        violacoes.append(f"{metodo.upper()} {caminho}")

        assert not violacoes, "tenant_id na query: " + ", ".join(violacoes)

    def test_admin_pode_ter_tenant_id_explicito(self, contrato) -> None:
        """A exceção precisa existir de verdade; senão o teste acima está só ignorando admin."""
        rotas_admin = [c for c in contrato["paths"] if c.startswith(PREFIXO_ADMIN)]

        assert rotas_admin, "nenhuma rota /v1/admin — a exceção do teste ficou sem objeto"


class TestAutenticacao:
    async def test_rota_de_emissao_sem_chave_nao_emite(self, cliente) -> None:
        """Sem credencial não há tenant — e sem tenant não há emissão."""
        resposta = await cliente.post(
            "/v1/emissoes",
            json={"valor": "10.00", "descricao": "sem chave", "competencia": "2026-11"},
        )

        assert resposta.status_code == 401
