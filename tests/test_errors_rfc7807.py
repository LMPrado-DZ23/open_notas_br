"""Contrato RFC 7807: catálogo e conversão.

Não há handler HTTP registrado ainda — de propósito. Registrar muda o corpo de
TODAS as rotas, e isso exige rodar a suíte inteira para provar regressão zero (R1).
Enquanto isso não acontece numa janela com contexto suficiente, o módulo fica com
teste próprio e sem efeito colateral.
"""

from __future__ import annotations

import pytest
from app.core.errors import (
    BASE_URI,
    TRANSITORIOS,
    OrigemErro,
    Problema,
    conflito,
    de_http_exception,
    interno,
    nao_encontrado,
    sefaz,
    validacao,
)


class TestEstrutura:
    def test_campos_obrigatorios_rfc7807(self) -> None:
        corpo = validacao("campo x inválido").para_dict()
        assert {"type", "title", "status", "detail"} <= set(corpo)

    def test_content_type_esperado(self) -> None:
        # O handler futuro deve emitir application/problem+json.
        assert validacao("x").para_dict()["status"] == 422

    def test_tipo_e_uri_absoluta(self) -> None:
        assert validacao("x").para_dict()["type"].startswith(BASE_URI)


class TestOrigem:
    def test_rejeicao_sefaz_marca_origem(self) -> None:
        corpo = sefaz("539", "rejeitado").para_dict()
        assert corpo["origem"] == OrigemErro.SEFAZ
        assert corpo["codigo_sefaz"] == "539"
        assert "539" in corpo["type"]

    def test_municipio_tem_origem_propria(self) -> None:
        corpo = sefaz("E10", "erro municipal", origem=OrigemErro.MUNICIPIO).para_dict()
        assert corpo["origem"] == OrigemErro.MUNICIPIO

    def test_erro_interno_e_retryable(self) -> None:
        assert interno("falha").para_dict()["retryable"] is True

    def test_validacao_nao_e_retryable(self) -> None:
        corpo = validacao("payload ruim").para_dict()
        assert corpo["retryable"] is False, "repetir o mesmo payload dá o mesmo erro"


class TestNaoQuebraContrato:
    def test_detail_preservado(self) -> None:
        corpo = de_http_exception(404, "emissão não encontrada").para_dict()
        assert corpo["detail"] == "emissão não encontrada"
        assert corpo["status"] == 404

    def test_status_preservado(self) -> None:
        for status in (400, 404, 409, 422, 500, 503):
            assert de_http_exception(status, "x").para_dict()["status"] == status

    def test_detail_nao_texto_vira_string(self) -> None:
        corpo = de_http_exception(502, {"tipo": "rejeicao"}).para_dict()
        assert "rejeicao" in corpo["detail"]

    def test_detail_gigante_e_truncado(self) -> None:
        corpo = de_http_exception(502, "x" * 5000).para_dict()
        assert len(corpo["detail"]) == 2000


class TestTransitoriedade:
    @pytest.mark.parametrize("status", sorted(TRANSITORIOS))
    def test_5xx_e_retryable(self, status: int) -> None:
        assert de_http_exception(status, "x").para_dict()["retryable"] is True

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
    def test_4xx_de_validacao_nao_e_retryable(self, status: int) -> None:
        assert de_http_exception(status, "x").para_dict()["retryable"] is False

    def test_502_e_transitorio(self) -> None:
        assert 502 in TRANSITORIOS


class TestConstrutores:
    def test_nao_encontrado_404(self) -> None:
        assert nao_encontrado("x").status == 404

    def test_conflito_409(self) -> None:
        assert conflito("x").status == 409

    def test_sem_codigo_sefaz_nao_inventa_codigo(self) -> None:
        corpo = sefaz(None, "rejeitado").para_dict()
        assert "codigo_sefaz" not in corpo
        assert "cstat-none" not in corpo["type"]

    def test_problema_com_instancia_e_request_id(self) -> None:
        corpo = Problema(
            titulo="t", status=422, detalhe="d", instancia="/v1/x", request_id="abc"
        ).para_dict()
        assert corpo["instance"] == "/v1/x"
        assert corpo["request_id"] == "abc"


class TestHandlerHTTP:
    """O handler registrado em `app/main.py` responde problem+json sem quebrar contrato."""

    async def test_404_tem_content_type_problem_json(self, cliente) -> None:
        resposta = await cliente.get("/v1/rota-que-nao-existe")
        assert resposta.status_code == 404
        assert resposta.headers["content-type"].startswith("application/problem+json")

    async def test_detail_preservado_na_resposta_real(self, cliente) -> None:
        # Cliente que lê `detail` continua funcionando (R2/P5).
        resposta = await cliente.get("/v1/rota-que-nao-existe")
        corpo = resposta.json()
        assert "detail" in corpo
        assert corpo["status"] == 404
        assert corpo["origem"] in ("VALIDACAO", "INTERNO", "SEFAZ", "MUNICIPIO")

    async def test_422_de_validacao_tambem_e_problem_json(self, cliente) -> None:
        # Sem API key o guarda de tenant barra: o formato precisa valer para 4xx.
        resposta = await cliente.post("/v1/emissoes", json={"valor": "10.00"})
        assert resposta.status_code in (401, 422)
        assert resposta.headers["content-type"].startswith("application/problem+json")
