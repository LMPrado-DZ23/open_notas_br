"""Testes de apuração e guias.

O ponto que mais importa: apuração soma **apenas documento autorizado**. Nota
rejeitada ou em erro não gera obrigação — se somasse, o contribuinte pagaria
tributo sobre nota que não existe.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.assessment import service as apuracao_service
from app.assessment.providers import (
    DadosApuracao,
    ErroDeGuia,
    ProvedorDas,
    ProvedorManDna,
    obter_provedor,
)
from app.core.config import Settings, get_settings
from app.db.models.enums import StatusFatura
from sqlalchemy import select

from tests.test_fase2_certificado import SENHA, gerar_pfx

COMPETENCIA = "2026-11"


@pytest.fixture
async def tenant(cliente) -> dict[str, Any]:
    resposta = await cliente.post(
        "/v1/tenants", json={"slug": "emissor-apuracao", "nome": "Apuração LTDA"}
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def cabecalho(tenant: dict[str, Any]) -> dict[str, str]:
    return {"X-API-Key": tenant["api_key"]}


@pytest.fixture
def adapter_mock(app_teste):
    app_teste.dependency_overrides[get_settings] = lambda: Settings(
        environment="test", nfse_adapter="mock"
    )
    yield
    app_teste.dependency_overrides.clear()


async def preparar(cliente, tenant: dict[str, Any]) -> None:
    """Configura fiscal e envia certificado para permitir emitir."""
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
    resposta = await cliente.post(
        "/v1/me/certificados",
        files={"arquivo": ("c.pfx", gerar_pfx(), "application/x-pkcs12")},
        data={"senha": SENHA.decode(), "apelido": "a1"},
        headers=cabecalho(tenant),
    )
    assert resposta.status_code == 201, resposta.text


async def emitir(cliente, tenant: dict[str, Any], chave: str, valor: str) -> dict[str, Any]:
    resposta = await cliente.post(
        "/v1/emissoes",
        json={
            "idempotency_key": chave,
            "valor": valor,
            "descricao": "Serviço prestado",
            "competencia": COMPETENCIA,
        },
        headers=cabecalho(tenant),
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


class TestConsolidacao:
    async def test_soma_documentos_autorizados(self, cliente, tenant, adapter_mock) -> None:
        await preparar(cliente, tenant)
        await emitir(cliente, tenant, "apuracao-ap-1", "100.00")
        await emitir(cliente, tenant, "apuracao-ap-2", "50.00")

        resposta = await cliente.post(
            "/v1/apuracoes",
            json={"competencia": COMPETENCIA},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()

        assert corpo["quantidade_documentos"] == 2
        assert corpo["total_servicos"] == "150.00"
        # ISS 5% sobre 150
        assert corpo["total_iss"] == "7.50"
        assert corpo["status"] == "closed"

    async def test_nao_soma_fatura_rejeitada(
        self, cliente, tenant, adapter_mock, sessao_db
    ) -> None:
        await preparar(cliente, tenant)
        await emitir(cliente, tenant, "apuracao-ap-ok", "100.00")

        # Simula uma fatura que falhou: não pode entrar na apuração.
        from app.db.models.invoice import Invoice

        resultado = await sessao_db.execute(
            select(Invoice).where(Invoice.idempotency_key == "apuracao-ap-ok")
        )
        fatura = resultado.scalar_one()
        rejeitada = Invoice(
            tenant_id=fatura.tenant_id,
            idempotency_key="ap-rejeitada",
            status=StatusFatura.REJEITADA,
            valor_servico="999.00",
            descricao_servico="não autorizada",
            competencia=COMPETENCIA,
        )
        sessao_db.add(rejeitada)
        await sessao_db.commit()

        resposta = await cliente.post(
            "/v1/apuracoes",
            json={"competencia": COMPETENCIA},
            headers=cabecalho(tenant),
        )
        corpo = resposta.json()
        assert corpo["quantidade_documentos"] == 1
        assert corpo["total_servicos"] == "100.00"

    async def test_reconsolidar_atualiza_e_nao_duplica(self, cliente, tenant, adapter_mock) -> None:
        await preparar(cliente, tenant)
        await emitir(cliente, tenant, "ap-unica", "100.00")

        primeira = await cliente.post(
            "/v1/apuracoes", json={"competencia": COMPETENCIA}, headers=cabecalho(tenant)
        )
        segunda = await cliente.post(
            "/v1/apuracoes", json={"competencia": COMPETENCIA}, headers=cabecalho(tenant)
        )

        assert primeira.json()["id"] == segunda.json()["id"]

        listagem = await cliente.get("/v1/apuracoes", headers=cabecalho(tenant))
        assert len(listagem.json()) == 1

    async def test_competencia_invalida_da_422(self, cliente, tenant) -> None:
        resposta = await cliente.post(
            "/v1/apuracoes", json={"competencia": "2026-13"}, headers=cabecalho(tenant)
        )
        assert resposta.status_code == 422

    async def test_competencia_vazia_nao_quebra(self, cliente, tenant) -> None:
        resposta = await cliente.post(
            "/v1/apuracoes", json={"competencia": "2026-05"}, headers=cabecalho(tenant)
        )
        assert resposta.status_code == 200
        assert resposta.json()["quantidade_documentos"] == 0
        assert resposta.json()["total_servicos"] == "0.00"


class TestGuia:
    async def test_guia_man(self, cliente, tenant, adapter_mock) -> None:
        await preparar(cliente, tenant)
        await emitir(cliente, tenant, "apuracao-guia-1", "200.00")
        criada = await cliente.post(
            "/v1/apuracoes",
            json={"competencia": COMPETENCIA, "provedor": "man"},
            headers=cabecalho(tenant),
        )
        apuracao_id = criada.json()["id"]

        guia = await cliente.post(f"/v1/apuracoes/{apuracao_id}/guia", headers=cabecalho(tenant))
        assert guia.status_code == 200, guia.text
        corpo = guia.json()
        assert corpo["provedor"] == "man"
        assert corpo["numero"].startswith("DNA")
        assert corpo["valor"] == "10.00"
        assert corpo["linha_digitavel"]

        detalhe = await cliente.get(f"/v1/apuracoes/{apuracao_id}", headers=cabecalho(tenant))
        assert detalhe.json()["guia_numero"] == corpo["numero"]

    async def test_guia_das(self, cliente, tenant, adapter_mock) -> None:
        await preparar(cliente, tenant)
        await emitir(cliente, tenant, "apuracao-guia-das", "100.00")
        criada = await cliente.post(
            "/v1/apuracoes",
            json={"competencia": COMPETENCIA, "provedor": "das"},
            headers=cabecalho(tenant),
        )
        guia = await cliente.post(
            f"/v1/apuracoes/{criada.json()['id']}/guia", headers=cabecalho(tenant)
        )
        assert guia.status_code == 200
        assert guia.json()["numero"].startswith("DAS")

    async def test_guia_municipal_se_recusa(self, cliente, tenant, adapter_mock) -> None:
        await preparar(cliente, tenant)
        await emitir(cliente, tenant, "apuracao-guia-mun", "100.00")
        criada = await cliente.post(
            "/v1/apuracoes",
            json={"competencia": COMPETENCIA, "provedor": "municipal"},
            headers=cabecalho(tenant),
        )
        resposta = await cliente.post(
            f"/v1/apuracoes/{criada.json()['id']}/guia", headers=cabecalho(tenant)
        )
        assert resposta.status_code == 422
        assert "município" in resposta.json()["detail"].lower()

        detalhe = await cliente.get(
            f"/v1/apuracoes/{criada.json()['id']}", headers=cabecalho(tenant)
        )
        assert detalhe.json()["status"] == "failed"


class TestProvedores:
    def test_man_exige_iss_positivo(self) -> None:
        dados = DadosApuracao(
            tenant_id="t",
            competencia=COMPETENCIA,
            total_servicos=__import__("decimal").Decimal("100"),
            total_iss=__import__("decimal").Decimal("0"),
            total_tributos=__import__("decimal").Decimal("1"),
            quantidade_documentos=1,
        )
        with pytest.raises(ErroDeGuia, match="ISS"):
            ProvedorManDna().gerar(dados)

    def test_das_exige_tributo_positivo(self) -> None:
        from decimal import Decimal

        dados = DadosApuracao(
            tenant_id="t",
            competencia=COMPETENCIA,
            total_servicos=Decimal("100"),
            total_iss=Decimal("5"),
            total_tributos=Decimal("0"),
            quantidade_documentos=1,
        )
        with pytest.raises(ErroDeGuia, match="tributos"):
            ProvedorDas().gerar(dados)

    def test_determinismo_da_guia(self) -> None:
        from decimal import Decimal

        dados = DadosApuracao(
            tenant_id="11111111-1111-1111-1111-111111111111",
            competencia=COMPETENCIA,
            total_servicos=Decimal("100"),
            total_iss=Decimal("5"),
            total_tributos=Decimal("1"),
            quantidade_documentos=1,
        )
        primeira = ProvedorManDna().gerar(dados)
        segunda = ProvedorManDna().gerar(dados)
        assert primeira.numero == segunda.numero
        assert primeira.linha_digitavel == segunda.linha_digitavel

    def test_provedor_desconhecido(self) -> None:
        with pytest.raises(Exception, match="não existe provedor"):
            obter_provedor("inexistente")  # type: ignore[arg-type]


class TestIsolamento:
    async def test_apuracao_de_outro_tenant_invisivel(self, cliente, tenant, adapter_mock) -> None:
        await preparar(cliente, tenant)
        await emitir(cliente, tenant, "apuracao-iso-1", "100.00")
        criada = await cliente.post(
            "/v1/apuracoes", json={"competencia": COMPETENCIA}, headers=cabecalho(tenant)
        )
        apuracao_id = criada.json()["id"]

        outro = await cliente.post(
            "/v1/tenants", json={"slug": "outro-apuracao", "nome": "Outro LTDA"}
        )
        consulta = await cliente.get(
            f"/v1/apuracoes/{apuracao_id}", headers=cabecalho(outro.json())
        )
        assert consulta.status_code == 404


class TestServico:
    async def test_competencia_do_mes(self) -> None:
        from datetime import date

        assert apuracao_service.competencia_de(date(2026, 3, 15)) == "2026-03"

    async def test_valida_competencia(self) -> None:
        assert apuracao_service.validar_competencia("2026-11") == "2026-11"
        with pytest.raises(apuracao_service.CompetenciaInvalida):
            apuracao_service.validar_competencia("26-11")
