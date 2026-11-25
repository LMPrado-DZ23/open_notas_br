"""Testes do catálogo de classificação tributária (cClassTrib).

O teste central é o do versionamento: o mesmo código tem descrição diferente em
anos diferentes no catálogo oficial. Se o produto deduplicasse por código,
validaria nota de 2026 contra a classificação de 2027 — erro silencioso.
"""

from __future__ import annotations

from datetime import date

import pytest
from app.tax import classificacoes


class TestCarregamento:
    def test_catalogo_nao_esta_vazio(self) -> None:
        assert len(classificacoes.todas()) > 100

    def test_metadados_declaram_a_fonte(self) -> None:
        meta = classificacoes.metadados()
        assert "calculadora" in (meta["fonte"] or "").lower()
        assert meta["total"] == len(classificacoes.todas())
        assert meta["codigos_distintos"] is not None
        assert meta["codigos_distintos"] < meta["total"]

    def test_codigos_tem_seis_digitos(self) -> None:
        assert all(len(c.codigo) == 6 and c.codigo.isdigit() for c in classificacoes.todas())

    def test_todas_tem_descricao(self) -> None:
        assert all(c.descricao.strip() for c in classificacoes.todas())


class TestVersionamento:
    def test_codigo_reutilizado_entre_versoes(self) -> None:
        # O SQL oficial tem 000001 em 2026 e em 2027, com descrições diferentes.
        ocorrencias = [c for c in classificacoes.todas() if c.codigo == "000001"]
        assert len(ocorrencias) >= 2
        descricoes = {c.descricao for c in ocorrencias}
        assert len(descricoes) >= 2, "o código deve reaparecer com descrição distinta"

    def test_busca_por_ano_respeita_vigencia(self) -> None:
        de_2026 = classificacoes.buscar("000001", quando=date(2026, 6, 1))
        de_2027 = classificacoes.buscar("000001", quando=date(2027, 6, 1))

        assert de_2026 is not None and de_2027 is not None
        assert de_2026.descricao != de_2027.descricao
        assert de_2026.inicio_vigencia < de_2027.inicio_vigencia

        # `vigente_em` é só o intervalo declarado; a substituição por versão mais
        # nova é resolvida em `vigentes_em`. Em 2027, o código deve vir da versão
        # de 2027, e não da de 2026.
        vigentes_2027 = {c.codigo: c for c in classificacoes.vigentes_em(date(2027, 6, 1))}
        assert vigentes_2027["000001"].descricao == de_2027.descricao
        assert vigentes_2027["000001"].descricao != de_2026.descricao

    def test_sem_ano_devolve_a_mais_recente(self) -> None:
        sem_ano = classificacoes.buscar("000001")
        com_ano = classificacoes.buscar("000001", quando=date(2027, 6, 1))
        assert sem_ano is not None and com_ano is not None
        assert sem_ano.inicio_vigencia == com_ano.inicio_vigencia

    def test_vigentes_em_2026_nao_incluem_2027(self) -> None:
        vigentes = classificacoes.vigentes_em(date(2026, 6, 1))
        assert vigentes
        assert all(c.inicio_vigencia <= "2026-06-01" for c in vigentes)

    def test_vigencia_com_fim(self) -> None:
        encerradas = [c for c in classificacoes.todas() if c.fim_vigencia]
        if encerradas:
            amostra = encerradas[0]
            assert not amostra.vigente_em(date(2100, 1, 1))

    def test_uma_versao_por_codigo_na_data(self) -> None:
        vigentes = classificacoes.vigentes_em(date(2026, 6, 1))
        codigos = [c.codigo for c in vigentes]
        assert len(codigos) == len(set(codigos)), "não pode haver duas versões do mesmo código"


class TestBusca:
    def test_busca_por_codigo(self) -> None:
        achada = classificacoes.buscar("000001")
        assert achada is not None
        assert achada.codigo == "000001"

    def test_codigo_inexistente(self) -> None:
        assert classificacoes.buscar("999999") is None

    def test_pesquisa_por_texto(self) -> None:
        achadas = classificacoes.pesquisar("tributadas integralmente", limite=10)
        assert achadas
        assert any("integralmente" in c.descricao.lower() for c in achadas)

    def test_pesquisa_vazia_lista_o_catalogo(self) -> None:
        assert len(classificacoes.pesquisar("", limite=5)) == 5

    def test_limite_e_respeitado(self) -> None:
        assert len(classificacoes.pesquisar("", limite=3)) == 3


class TestEndpoints:
    async def test_listar_classificacoes(self, cliente, tenant_autenticado) -> None:
        resposta = await cliente.get(
            "/v1/tax/classificacoes?limite=5", headers={"X-API-Key": tenant_autenticado}
        )
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert len(corpo) == 5
        assert {"codigo", "descricao"} <= set(corpo[0])

    async def test_filtrar_por_ano(self, cliente, tenant_autenticado) -> None:
        resposta = await cliente.get(
            "/v1/tax/classificacoes?ano=2026&busca=000001",
            headers={"X-API-Key": tenant_autenticado},
        )
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo
        assert all(item["inicio_vigencia"] <= "2026-12-31" for item in corpo)

    async def test_obter_por_codigo_com_ano(self, cliente, tenant_autenticado) -> None:
        resposta = await cliente.get(
            "/v1/tax/classificacoes/000001?ano=2027",
            headers={"X-API-Key": tenant_autenticado},
        )
        assert resposta.status_code == 200
        assert resposta.json()["codigo"] == "000001"

    async def test_catalogo_metadados(self, cliente, tenant_autenticado) -> None:
        resposta = await cliente.get(
            "/v1/tax/classificacoes/catalogo", headers={"X-API-Key": tenant_autenticado}
        )
        assert resposta.status_code == 200
        assert resposta.json()["total"] > 100

    async def test_codigo_inexistente_da_404(self, cliente, tenant_autenticado) -> None:
        resposta = await cliente.get(
            "/v1/tax/classificacoes/999999", headers={"X-API-Key": tenant_autenticado}
        )
        assert resposta.status_code == 404

    async def test_exige_credencial(self, cliente) -> None:
        assert (await cliente.get("/v1/tax/classificacoes")).status_code == 401


@pytest.fixture
async def tenant_autenticado(cliente) -> str:
    """API key de um tenant novo, para rotas que exigem credencial."""
    resposta = await cliente.post(
        "/v1/tenants", json={"slug": "catalogo-teste", "nome": "Catálogo Teste LTDA"}
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["api_key"]
