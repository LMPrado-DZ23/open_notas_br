"""Testes dos conectores DZ23 e Brizu.

O ponto crítico é idempotência entre sistemas: o parceiro reenvia o mesmo evento
(webhook repetido, retry de rede). Isso não pode gerar segunda nota — e não pode
devolver erro 500, porque o parceiro vai continuar tentando.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.core.config import Settings, get_settings
from app.integrations.base import ErroDeIntegracao, para_decimal
from app.integrations.brizu.conector import ConectorBrizu
from app.integrations.dz23.conector import ConectorDz23

from tests.test_fase2_certificado import SENHA, gerar_pfx


@pytest.fixture
async def tenant(cliente) -> dict[str, Any]:
    resposta = await cliente.post(
        "/v1/tenants", json={"slug": "parceiro-tenant", "nome": "Parceiro LTDA"}
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def cabecalho(tenant: dict[str, Any]) -> dict[str, str]:
    return {"X-API-Key": tenant["api_key"]}


@pytest.fixture
async def pronto(cliente, tenant, app_teste) -> dict[str, Any]:
    """Tenant com config fiscal e certificado, emitindo com dublê."""
    app_teste.dependency_overrides[get_settings] = lambda: Settings(
        environment="test", nfse_adapter="mock"
    )
    await cliente.put(
        "/v1/me/config-fiscal",
        json={
            "municipio_ibge": "3550308",
            "uf": "SP",
            "ambiente": "homologacao",
            "codigo_tributacao_nacional": "010701",
            "serie_dps": "1",
            "aliquota_iss": 0.05,
        },
        headers=cabecalho(tenant),
    )
    await cliente.post(
        "/v1/me/certificados",
        files={"arquivo": ("c.pfx", gerar_pfx(), "application/x-pkcs12")},
        data={"senha": SENHA.decode(), "apelido": "a1"},
        headers=cabecalho(tenant),
    )
    yield tenant
    app_teste.dependency_overrides.clear()


class TestConectorDz23:
    def test_payload_completo(self) -> None:
        pedido = ConectorDz23().interpretar(
            {
                "evento_id": "venda-900",
                "valor": 150.5,
                "descricao": "Corte + barba",
                "competencia": "2026-11",
                "cliente": {
                    "nome": "Ana Silva",
                    "documento": "11144477735",
                    "email": "ana@exemplo.test",
                },
                "pedido_id": "PED-77",
            }
        )
        assert pedido.parceiro == "dz23"
        assert pedido.idempotency_key == "dz23:venda-900"
        assert pedido.valor == para_decimal(150.5, "valor")
        assert pedido.tomador_nome == "Ana Silva"
        assert pedido.referencia_externa == "PED-77"

    def test_sem_evento_id(self) -> None:
        with pytest.raises(ErroDeIntegracao, match="evento_id"):
            ConectorDz23().interpretar({"valor": 10, "descricao": "x"})

    def test_sem_valor(self) -> None:
        with pytest.raises(ErroDeIntegracao, match="valor"):
            ConectorDz23().interpretar({"evento_id": "e1", "descricao": "x"})

    def test_valor_zero(self) -> None:
        with pytest.raises(ErroDeIntegracao, match="maior que zero"):
            ConectorDz23().interpretar({"evento_id": "e1", "valor": 0, "descricao": "x"})

    def test_cliente_nao_objeto(self) -> None:
        with pytest.raises(ErroDeIntegracao, match="cliente"):
            ConectorDz23().interpretar(
                {"evento_id": "e1", "valor": 10, "descricao": "x", "cliente": "Ana"}
            )

    def test_valor_em_texto_brasileiro(self) -> None:
        pedido = ConectorDz23().interpretar(
            {"evento_id": "e2", "valor": "R$ 1.234,56", "descricao": "x"}
        )
        assert str(pedido.valor) == "1234.56"

    def test_sem_cliente_ainda_e_valido(self) -> None:
        pedido = ConectorDz23().interpretar(
            {"evento_id": "e3", "valor": 10, "descricao": "serviço"}
        )
        assert pedido.tomador_nome is None


class TestConectorBrizu:
    def test_usa_servico_como_descricao(self) -> None:
        pedido = ConectorBrizu().interpretar(
            {"evento_id": "ag-1", "valor": 90, "servico": "Corte feminino"}
        )
        assert pedido.descricao == "Corte feminino"
        assert pedido.idempotency_key == "brizu:ag-1"

    def test_exige_servico(self) -> None:
        with pytest.raises(ErroDeIntegracao, match="servico"):
            ConectorBrizu().interpretar({"evento_id": "ag-2", "valor": 90})

    def test_prefixo_diferente_do_dz23(self) -> None:
        dz = ConectorDz23().interpretar({"evento_id": "X1", "valor": 10, "descricao": "a"})
        bz = ConectorBrizu().interpretar({"evento_id": "X1", "valor": 10, "servico": "a"})
        assert dz.idempotency_key != bz.idempotency_key, (
            "mesmo id em parceiros diferentes não pode colidir"
        )


class TestEndpointDz23:
    async def test_emite_na_primeira_chamada(self, cliente, pronto) -> None:
        resposta = await cliente.post(
            "/v1/integracoes/dz23/vendas",
            json={
                "evento_id": "dz-e2e-1",
                "valor": 100.00,
                "descricao": "Serviço",
                "cliente": {"nome": "Cliente DZ"},
            },
            headers=cabecalho(pronto),
        )
        assert resposta.status_code == 201, resposta.text
        corpo = resposta.json()
        assert corpo["ja_existia"] is False
        assert len(corpo["chave"]) == 50

    async def test_reenvio_devolve_200(self, cliente, pronto) -> None:
        payload = {"evento_id": "dz-e2e-2", "valor": 50.00, "descricao": "Serviço"}
        primeira = await cliente.post(
            "/v1/integracoes/dz23/vendas", json=payload, headers=cabecalho(pronto)
        )
        segunda = await cliente.post(
            "/v1/integracoes/dz23/vendas", json=payload, headers=cabecalho(pronto)
        )
        assert primeira.status_code == 201
        assert segunda.status_code == 200
        assert segunda.json()["ja_existia"] is True
        assert segunda.json()["invoice_id"] == primeira.json()["invoice_id"]

    async def test_payload_invalido_422(self, cliente, pronto) -> None:
        resposta = await cliente.post(
            "/v1/integracoes/dz23/vendas",
            json={"valor": 10},
            headers=cabecalho(pronto),
        )
        assert resposta.status_code == 422
        assert "evento_id" in str(resposta.json()["detail"])


class TestEndpointBrizu:
    async def test_emite_com_servico(self, cliente, pronto) -> None:
        resposta = await cliente.post(
            "/v1/integracoes/brizu/atendimentos",
            json={
                "evento_id": "bz-e2e-1",
                "valor": 90.00,
                "servico": "Escova",
                "agendamento_id": "AG-9",
            },
            headers=cabecalho(pronto),
        )
        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["parceiro"] == "brizu"

    async def test_reenvio_idempotente(self, cliente, pronto) -> None:
        payload = {"evento_id": "bz-e2e-2", "valor": 30.00, "servico": "Corte"}
        await cliente.post(
            "/v1/integracoes/brizu/atendimentos", json=payload, headers=cabecalho(pronto)
        )
        segunda = await cliente.post(
            "/v1/integracoes/brizu/atendimentos", json=payload, headers=cabecalho(pronto)
        )
        assert segunda.status_code == 200
        assert segunda.json()["ja_existia"] is True


class TestIsolamento:
    async def test_mesmo_evento_em_tenants_diferentes(self, cliente, pronto, app_teste) -> None:
        payload = {"evento_id": "compartilhado-1", "valor": 10.00, "descricao": "x"}
        primeira = await cliente.post(
            "/v1/integracoes/dz23/vendas", json=payload, headers=cabecalho(pronto)
        )
        assert primeira.status_code == 201

        outro = await cliente.post(
            "/v1/tenants", json={"slug": "outro-parceiro", "nome": "Outro LTDA"}
        )
        outra_chave = outro.json()["api_key"]
        # Outro tenant sem config/certificado: a emissão falha por falta de
        # certificado, mas o evento NÃO pode reaproveitar a nota do primeiro.
        segunda = await cliente.post(
            "/v1/integracoes/dz23/vendas",
            json=payload,
            headers={"X-API-Key": outra_chave},
        )
        assert segunda.status_code != 200 or segunda.json()["ja_existia"] is False
