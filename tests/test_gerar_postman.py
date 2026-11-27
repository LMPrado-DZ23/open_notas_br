"""Coleção Postman derivada do contrato (§63).

O que precisa ser provado:

1. a coleção versionada **não diverge** do `openapi.json` (`--check`);
2. toda requisição da coleção corresponde a uma rota que existe no contrato — nada de endpoint
   inventado, nada de rota removida que ficou na coleção;
3. o corpo é **esqueleto**, não exemplo de negócio inventado (CNPJ/valor fictício em coleção de
   gateway fiscal vira dado errado na mão de quem integra).
"""

from __future__ import annotations

import json

import pytest
from scripts import gerar_postman


@pytest.fixture
def contrato() -> dict:
    return json.loads(gerar_postman.OPENAPI.read_text(encoding="utf-8"))


class TestAntiDrift:
    def test_colecao_esta_em_dia_com_o_contrato(self) -> None:
        assert gerar_postman.main(["--check"]) == 0, (
            "docs/postman_collection.json divergiu do openapi.json. "
            "Rode: python -m scripts.gerar_postman"
        )

    def test_toda_requisicao_existe_no_contrato(self, contrato) -> None:
        colecao = json.loads(gerar_postman.DESTINO.read_text(encoding="utf-8"))
        caminhos = set(contrato["paths"])

        for pasta in colecao["item"]:
            for requisicao in pasta["item"]:
                caminho = "/" + "/".join(requisicao["request"]["url"]["path"])
                assert caminho in caminhos, f"rota inexistente na coleção: {caminho}"

    def test_contrato_nao_tem_rota_fora_da_colecao(self, contrato) -> None:
        colecao = json.loads(gerar_postman.DESTINO.read_text(encoding="utf-8"))
        na_colecao = {
            "/" + "/".join(req["request"]["url"]["path"])
            for pasta in colecao["item"]
            for req in pasta["item"]
        }
        metodos_ignorados = {"head", "options", "trace"}
        for caminho, operacoes in contrato["paths"].items():
            for metodo in operacoes:
                if metodo.lower() in metodos_ignorados:
                    continue
                assert caminho in na_colecao, f"rota fora da coleção: {metodo} {caminho}"


class TestCorpo:
    def test_corpo_e_esqueleto_e_nao_dado_inventado(self, contrato) -> None:
        colecao = json.loads(gerar_postman.DESTINO.read_text(encoding="utf-8"))

        corpos = [
            requisicao["request"]["body"]["raw"]
            for pasta in colecao["item"]
            for requisicao in pasta["item"]
            if "body" in requisicao["request"]
        ]
        assert corpos, "nenhuma requisição com corpo — a coleção não serve para testar POST"

        for corpo in corpos:
            # Esqueleto válido em JSON…
            json.loads(corpo)
            # …e sem dado de negócio inventado.
            for proibido in ("00000000000", "11.222.333", "12345678000199", "R$ "):
                assert proibido not in corpo, f"dado inventado no corpo: {proibido}"

    def test_api_key_usa_variavel_do_postman(self) -> None:
        colecao = json.loads(gerar_postman.DESTINO.read_text(encoding="utf-8"))
        requisicao = colecao["item"][0]["item"][0]

        cabecalhos = {c["key"]: c["value"] for c in requisicao["request"]["header"]}
        assert cabecalhos["X-API-Key"] == "{{api_key}}"


class TestEsqueleto:
    def test_string_vira_vazia_e_inteiro_vira_zero(self) -> None:
        assert gerar_postman._esqueleto({"type": "string"}) == ""
        assert gerar_postman._esqueleto({"type": "integer"}) == 0
        assert gerar_postman._esqueleto({"type": "boolean"}) is False

    def test_respeita_exemplo_do_schema_quando_existe(self) -> None:
        assert gerar_postman._esqueleto({"type": "string", "example": "abc"}) == "abc"

    def test_objeto_aninhado_e_derivado(self) -> None:
        schema = {
            "type": "object",
            "properties": {"nome": {"type": "string"}, "n": {"type": "integer"}},
        }
        assert gerar_postman._esqueleto(schema) == {"nome": "", "n": 0}
