"""Registro genérico de eventos: catálogo acionável, não só documentado."""

from __future__ import annotations

from typing import Any

import pytest
from app.core.config import Settings, get_settings
from app.db.models.invoice import InvoiceEvent
from app.nfse import eventos as eventos_service
from sqlalchemy import select

from tests.test_fase2_certificado import SENHA, gerar_pfx

MOTIVO = "Rejeicao do servico por nao execucao do contrato"


@pytest.fixture
async def pronto(cliente, app_teste):
    criado = await cliente.post(
        "/v1/tenants", json={"slug": "evento-tenant", "nome": "Evento LTDA"}
    )
    tenant = criado.json()
    cabecalho = {"X-API-Key": tenant["api_key"]}

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
        headers=cabecalho,
    )
    await cliente.post(
        "/v1/me/certificados",
        files={"arquivo": ("c.pfx", gerar_pfx(), "application/x-pkcs12")},
        data={"senha": SENHA.decode(), "apelido": "a1"},
        headers=cabecalho,
    )
    emissao = await cliente.post(
        "/v1/emissoes",
        json={
            "idempotency_key": "evento-emissao-001",
            "valor": "200.00",
            "descricao": "Servico com evento",
            "competencia": "2026-11",
        },
        headers=cabecalho,
    )
    assert emissao.status_code == 201, emissao.text

    yield {"tenant": tenant, "cabecalho": cabecalho, "emissao": emissao.json()}
    app_teste.dependency_overrides.clear()


def cabecalho(pronto: dict[str, Any]) -> dict[str, str]:
    return pronto["cabecalho"]


class TestDisponiveis:
    async def test_lista_sem_cancelamento(self, cliente, pronto) -> None:
        resposta = await cliente.get("/v1/emissoes/eventos/disponiveis", headers=cabecalho(pronto))
        assert resposta.status_code == 200
        tipos = resposta.json()["tipos"]
        assert "101101" not in tipos, "cancelamento tem rota própria"
        assert "202201" in tipos

    async def test_incluir_oficio(self, cliente, pronto) -> None:
        resposta = await cliente.get(
            "/v1/emissoes/eventos/disponiveis?incluir_oficio=true",
            headers=cabecalho(pronto),
        )
        assert "305101" in resposta.json()["tipos"]


class TestRegistro:
    async def test_confirmacao_do_prestador(self, cliente, pronto) -> None:
        resposta = await cliente.post(
            f"/v1/emissoes/{pronto['emissao']['invoice_id']}/eventos",
            json={"codigo": "202201", "campos": {}},
            headers=cabecalho(pronto),
        )
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["codigo"] == "202201"

    async def test_rejeicao_com_motivo(self, cliente, pronto) -> None:
        resposta = await cliente.post(
            f"/v1/emissoes/{pronto['emissao']['invoice_id']}/eventos",
            json={"codigo": "202205", "campos": {"cMotivo": "1", "xMotivo": MOTIVO}},
            headers=cabecalho(pronto),
        )
        assert resposta.status_code == 200, resposta.text

    async def test_cancelamento_recusado_com_ponteiro(self, cliente, pronto) -> None:
        resposta = await cliente.post(
            f"/v1/emissoes/{pronto['emissao']['invoice_id']}/eventos",
            json={"codigo": "101101", "campos": {"cMotivo": "1", "xMotivo": MOTIVO}},
            headers=cabecalho(pronto),
        )
        assert resposta.status_code == 422
        assert "cancelamento" in resposta.json()["detail"].lower()

    async def test_tipo_de_oficio_recusado(self, cliente, pronto) -> None:
        resposta = await cliente.post(
            f"/v1/emissoes/{pronto['emissao']['invoice_id']}/eventos",
            json={"codigo": "305101", "campos": {}},
            headers=cabecalho(pronto),
        )
        assert resposta.status_code == 422
        assert "ofício" in resposta.json()["detail"].lower()

    async def test_tipo_inexistente_da_422(self, cliente, pronto) -> None:
        resposta = await cliente.post(
            f"/v1/emissoes/{pronto['emissao']['invoice_id']}/eventos",
            json={"codigo": "999999", "campos": {}},
            headers=cabecalho(pronto),
        )
        assert resposta.status_code == 422

    async def test_campo_obrigatorio_ausente_da_422(self, cliente, pronto) -> None:
        resposta = await cliente.post(
            f"/v1/emissoes/{pronto['emissao']['invoice_id']}/eventos",
            json={"codigo": "202205", "campos": {"xMotivo": MOTIVO}},
            headers=cabecalho(pronto),
        )
        assert resposta.status_code == 422
        assert "cMotivo" in str(resposta.json()["detail"])

    async def test_motivo_curto_da_422(self, cliente, pronto) -> None:
        resposta = await cliente.post(
            f"/v1/emissoes/{pronto['emissao']['invoice_id']}/eventos",
            json={"codigo": "202205", "campos": {"cMotivo": "1", "xMotivo": "curto"}},
            headers=cabecalho(pronto),
        )
        assert resposta.status_code == 422

    async def test_emissao_inexistente_da_404(self, cliente, pronto) -> None:
        import uuid

        resposta = await cliente.post(
            f"/v1/emissoes/{uuid.uuid4()}/eventos",
            json={"codigo": "202201", "campos": {}},
            headers=cabecalho(pronto),
        )
        assert resposta.status_code == 404

    async def test_registra_trilha(self, cliente, pronto, sessao_db) -> None:
        await cliente.post(
            f"/v1/emissoes/{pronto['emissao']['invoice_id']}/eventos",
            json={"codigo": "202201", "campos": {}},
            headers=cabecalho(pronto),
        )
        eventos = (
            (
                await sessao_db.execute(
                    select(InvoiceEvent).where(InvoiceEvent.tipo == "evento_202201")
                )
            )
            .scalars()
            .all()
        )
        assert eventos
        evento = eventos[-1]
        assert evento.requisicao["codigo"] == "202201"
        assert evento.requisicao["id_pedido"].startswith("PRE")
        assert evento.status == "registrado"

    async def test_sequencia_avanca_no_mesmo_tipo(self, cliente, pronto, sessao_db) -> None:
        for _ in range(2):
            await cliente.post(
                f"/v1/emissoes/{pronto['emissao']['invoice_id']}/eventos",
                json={"codigo": "202201", "campos": {}},
                headers=cabecalho(pronto),
            )
        sequencias = (
            (
                await sessao_db.execute(
                    select(InvoiceEvent.sequencia)
                    .where(InvoiceEvent.tipo == "evento_202201")
                    .order_by(InvoiceEvent.sequencia)
                )
            )
            .scalars()
            .all()
        )
        assert sequencias == sorted(set(sequencias)), "sequência não pode repetir"
        assert len(sequencias) >= 2


class TestValidacaoDeTipo:
    def test_cancelamento_reservado(self) -> None:
        with pytest.raises(eventos_service.TipoReservado):
            eventos_service.validar_tipo("101101")

    def test_oficio_recusado_por_padrao(self) -> None:
        with pytest.raises(eventos_service.EventoNaoAplicavel):
            eventos_service.validar_tipo("305101")

    def test_oficio_aceito_quando_permitido(self) -> None:
        eventos_service.validar_tipo("305101", permitir_oficio=True)

    def test_tipos_disponiveis_excluem_cancelamento(self) -> None:
        assert "101101" not in eventos_service.tipos_disponiveis()
        assert "202201" in eventos_service.tipos_disponiveis()
