"""Rotas de municípios: paginação, filtros, 404 e 422."""

from __future__ import annotations

import pytest
from app.db.models.municipio import MunicipioNFSe, ProvedorNFSe


@pytest.fixture
async def municipios(sessao_db):
    for codigo, nome, uf, prov in [
        ("5200258", "Aguas Lindas de Goias", "GO", ProvedorNFSe.NACIONAL_REST),
        ("5208707", "Goiania", "GO", ProvedorNFSe.NACIONAL_REST),
        ("3550308", "Sao Paulo", "SP", ProvedorNFSe.ABRASF_2_04),
    ]:
        sessao_db.add(
            MunicipioNFSe(
                codigo_ibge=codigo,
                nome=nome,
                uf=uf,
                provedor=prov,
                fonte_url="https://servicodados.ibge.gov.br/api/v1/localidades/municipios",
            )
        )
    await sessao_db.commit()


class TestListagem:
    async def test_lista_todos(self, cliente, municipios) -> None:
        resposta = await cliente.get("/v1/municipios")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["total"] == 3
        assert len(corpo["itens"]) == 3

    async def test_filtra_por_uf(self, cliente, municipios) -> None:
        corpo = (await cliente.get("/v1/municipios?uf=GO")).json()
        assert corpo["total"] == 2
        assert {m["uf"] for m in corpo["itens"]} == {"GO"}

    async def test_filtra_por_provedor(self, cliente, municipios) -> None:
        corpo = (await cliente.get("/v1/municipios?provedor=abrasf_2_04")).json()
        assert corpo["total"] == 1
        assert corpo["itens"][0]["codigo_ibge"] == "3550308"

    async def test_paginacao_nao_altera_o_total(self, cliente, municipios) -> None:
        corpo = (await cliente.get("/v1/municipios?limite=1&deslocamento=0")).json()
        assert corpo["total"] == 3, "total é do filtro, não da página"
        assert len(corpo["itens"]) == 1

    async def test_fonte_url_exposta(self, cliente, municipios) -> None:
        # R3: o cliente tem direito de conferir de onde veio a configuração.
        corpo = (await cliente.get("/v1/municipios")).json()
        assert all(m["fonte_url"].startswith("https://") for m in corpo["itens"])

    async def test_sem_municipios_devolve_lista_vazia(self, cliente) -> None:
        corpo = (await cliente.get("/v1/municipios")).json()
        assert corpo["total"] == 0
        assert corpo["itens"] == []


class TestDetalhe:
    async def test_obtem_por_codigo(self, cliente, municipios) -> None:
        resposta = await cliente.get("/v1/municipios/5200258")
        assert resposta.status_code == 200
        assert resposta.json()["nome"] == "Aguas Lindas de Goias"

    async def test_inexistente_da_404(self, cliente, municipios) -> None:
        resposta = await cliente.get("/v1/municipios/9999999")
        assert resposta.status_code == 404

    async def test_codigo_curto_da_422(self, cliente) -> None:
        resposta = await cliente.get("/v1/municipios/123")
        assert resposta.status_code == 422

    async def test_codigo_nao_numerico_da_422(self, cliente) -> None:
        resposta = await cliente.get("/v1/municipios/abcdefg")
        assert resposta.status_code == 422
