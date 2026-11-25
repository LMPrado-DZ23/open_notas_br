"""Testes da API HTTP.

Pulados quando o extra ``notasbr[api]`` não está instalado — o núcleo não depende
de FastAPI e a suíte precisa passar sem ele.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="extra notasbr[api] não instalado")
pytest.importorskip("httpx", reason="TestClient do FastAPI exige httpx")

from fastapi.testclient import TestClient

from notasbr.api import criar_app
from tests.construir import com_campo, nfe


@pytest.fixture
def cliente() -> TestClient:
    return TestClient(criar_app())


class TestMeta:
    def test_saude(self, cliente: TestClient) -> None:
        resposta = cliente.get("/v1/saude")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["ok"] is True
        assert corpo["regras"] > 20

    def test_regras(self, cliente: TestClient) -> None:
        resposta = cliente.get("/v1/regras")
        assert resposta.status_code == 200
        assert resposta.json()["total"] == len(resposta.json()["regras"])

    def test_limitacoes(self, cliente: TestClient) -> None:
        resposta = cliente.get("/v1/limitacoes")
        assert resposta.status_code == 200
        assert any("XSD" in item for item in resposta.json()["limitacoes"])


class TestAuditar:
    def test_upload_limpo(self, cliente: TestClient) -> None:
        resposta = cliente.post(
            "/v1/auditar",
            files={"arquivo": ("nota.xml", nfe(), "application/xml")},
        )
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["documento"]["tipo"] == "nfe"
        assert corpo["resumo"]["erros"] == 0
        assert corpo["arquivo"] == "nota.xml"

    def test_upload_com_erro(self, cliente: TestClient) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/ide/cDV", "9")
        resposta = cliente.post(
            "/v1/auditar", files={"arquivo": ("nota.xml", xml, "application/xml")}
        )
        assert resposta.status_code == 200
        assert resposta.json()["resumo"]["situacao"] == "reprovado"

    def test_xml_invalido_da_422(self, cliente: TestClient) -> None:
        resposta = cliente.post(
            "/v1/auditar",
            files={"arquivo": ("x.xml", b"nao e xml", "application/xml")},
        )
        assert resposta.status_code == 422

    def test_documento_nao_suportado_da_422(self, cliente: TestClient) -> None:
        resposta = cliente.post(
            "/v1/auditar", files={"arquivo": ("x.xml", b"<outro/>", "application/xml")}
        )
        assert resposta.status_code == 422

    def test_limite_de_bytes(self, cliente: TestClient) -> None:
        resposta = cliente.post(
            "/v1/auditar?limite_bytes=100",
            files={"arquivo": ("nota.xml", nfe(), "application/xml")},
        )
        assert resposta.status_code == 413


class TestConsulta:
    def test_chave_valida(self, cliente: TestClient) -> None:
        chave = "35250111222333000181550010000001231123456782"
        resposta = cliente.get(f"/v1/chave/{chave}")
        assert resposta.status_code == 200
        assert resposta.json()["uf"] == "SP"

    def test_chave_invalida(self, cliente: TestClient) -> None:
        assert cliente.get("/v1/chave/123").status_code == 422

    def test_cnpj(self, cliente: TestClient) -> None:
        corpo = cliente.get("/v1/cnpj/11222333000181").json()
        assert corpo["valido"] is True
        assert corpo["formatado"] == "11.222.333/0001-81"

    def test_cpf(self, cliente: TestClient) -> None:
        corpo = cliente.get("/v1/cpf/11144477735").json()
        assert corpo["valido"] is True
