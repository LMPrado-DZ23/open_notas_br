"""Testes da rota de representação a partir de XML autorizado."""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest
from pypdf import PdfReader

from tests.construir import nfe, sem_campo

VOLUMES = [{"qVol": "2", "esp": "CAIXA", "pesoB": "13.200"}]


@pytest.fixture
async def tenant(cliente) -> dict[str, Any]:
    resposta = await cliente.post("/v1/tenants", json={"slug": "repr-tenant", "nome": "Repr LTDA"})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def cabecalho(tenant: dict[str, Any]) -> dict[str, str]:
    return {"X-API-Key": tenant["api_key"]}


def texto(pdf: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages)


class TestListagem:
    async def test_lista_formatos(self, cliente, tenant) -> None:
        resposta = await cliente.get("/v1/representacoes", headers=cabecalho(tenant))
        assert resposta.status_code == 200
        formatos = {(i["documento"], i["formato"]) for i in resposta.json()}
        assert ("nfe", "danfe") in formatos
        assert ("nfe", "etiquetas") in formatos
        assert ("nfe", "danfe_simplificado") in formatos
        assert ("nfse", "danfse") in formatos


class TestGeracao:
    async def test_danfe(self, cliente, tenant) -> None:
        resposta = await cliente.post(
            "/v1/representacoes?formato=danfe",
            files={"arquivo": ("nfe.xml", nfe(volumes=VOLUMES), "application/xml")},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 200, resposta.text
        assert resposta.headers["content-type"] == "application/pdf"
        assert resposta.content.startswith(b"%PDF")
        assert "DANFE" in texto(resposta.content)

    async def test_danfe_simplificado(self, cliente, tenant) -> None:
        resposta = await cliente.post(
            "/v1/representacoes?formato=danfe_simplificado",
            files={"arquivo": ("nfe.xml", nfe(), "application/xml")},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 200
        assert "DANFE SIMPLIFICADO" in texto(resposta.content)

    async def test_etiquetas_usa_volumes_do_xml(self, cliente, tenant) -> None:
        resposta = await cliente.post(
            "/v1/representacoes?formato=etiquetas",
            files={"arquivo": ("nfe.xml", nfe(volumes=VOLUMES), "application/xml")},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 200
        corpo = texto(resposta.content)
        assert "Volume 1/2" in corpo
        assert "Volume 2/2" in corpo

    async def test_etiquetas_com_quantidade_explicita(self, cliente, tenant) -> None:
        resposta = await cliente.post(
            "/v1/representacoes?formato=etiquetas&volumes=3",
            files={"arquivo": ("nfe.xml", nfe(), "application/xml")},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 200
        assert "Volume 1/3" in texto(resposta.content)

    async def test_formato_desconhecido_da_422(self, cliente, tenant) -> None:
        resposta = await cliente.post(
            "/v1/representacoes?formato=formato_que_nao_existe",
            files={"arquivo": ("nfe.xml", nfe(), "application/xml")},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 422
        detalhe = str(resposta.json()["detail"])
        assert "danfe" in detalhe, "o erro deve listar o que existe"

    async def test_xml_invalido_da_422(self, cliente, tenant) -> None:
        resposta = await cliente.post(
            "/v1/representacoes?formato=danfe",
            files={"arquivo": ("ruim.xml", b"<nfeProc><NFe>", "application/xml")},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 422

    async def test_arquivo_vazio_da_422(self, cliente, tenant) -> None:
        resposta = await cliente.post(
            "/v1/representacoes?formato=danfe",
            files={"arquivo": ("vazio.xml", b"", "application/xml")},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 422

    async def test_exige_credencial(self, cliente) -> None:
        resposta = await cliente.post(
            "/v1/representacoes?formato=danfe",
            files={"arquivo": ("nfe.xml", nfe(), "application/xml")},
        )
        assert resposta.status_code == 401


class TestFidelidade:
    async def test_dados_do_xml_aparecem(self, cliente, tenant) -> None:
        resposta = await cliente.post(
            "/v1/representacoes?formato=danfe",
            files={"arquivo": ("nfe.xml", nfe(volumes=VOLUMES), "application/xml")},
            headers=cabecalho(tenant),
        )
        corpo = texto(resposta.content)
        assert "Cliente Exemplo SA" in corpo
        assert "Empresa Exemplo LTDA" in corpo
        assert "1.000,00" in corpo

    async def test_campo_ausente_e_avisado(self, cliente, tenant) -> None:
        xml = sem_campo(nfe(), "NFe/infNFe/dest/xNome")
        resposta = await cliente.post(
            "/v1/representacoes?formato=danfe",
            files={"arquivo": ("nfe.xml", xml, "application/xml")},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 200
        assert "Campos não encontrados" in texto(resposta.content)
