"""Cancelamento pela API: fluxo completo com dublê.

Cobre o que o usuário vê: só nota autorizada cancela, motivo inválido é recusado
antes de qualquer chamada, e a nota cancelada permanece auditável.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings, get_settings
from app.db.models.enums import StatusFatura
from app.db.models.invoice import InvoiceEvent
from sqlalchemy import select

from tests.test_fase2_certificado import SENHA, gerar_pfx

MOTIVO_OK = "Cancelamento solicitado pelo cliente apos emissao"


@pytest.fixture
async def pronto(cliente, app_teste, sessao_db):
    """Tenant configurado, com certificado e uma nota autorizada."""
    criado = await cliente.post(
        "/v1/tenants", json={"slug": "cancel-tenant", "nome": "Cancel LTDA"}
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
            "idempotency_key": "cancel-emissao-001",
            "valor": "100.00",
            "descricao": "Servico a cancelar",
            "competencia": "2026-11",
        },
        headers=cabecalho,
    )
    assert emissao.status_code == 201, emissao.text

    yield {"tenant": tenant, "cabecalho": cabecalho, "emissao": emissao.json()}
    app_teste.dependency_overrides.clear()


class TestMotivos:
    async def test_lista_motivos(self, cliente, pronto) -> None:
        resposta = await cliente.get(
            "/v1/emissoes/cancelamento/motivos", headers=pronto["cabecalho"]
        )
        assert resposta.status_code == 200
        assert set(resposta.json()) == {"1", "2", "9"}


class TestCancelamento:
    async def test_cancela_nota_autorizada(self, cliente, pronto) -> None:
        invoice_id = pronto["emissao"]["invoice_id"]
        resposta = await cliente.post(
            f"/v1/emissoes/{invoice_id}/cancelamento",
            json={"c_motivo": "1", "x_motivo": MOTIVO_OK},
            headers=pronto["cabecalho"],
        )
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["status"] == "cancelled"
        assert len(corpo["chave"]) == 50

    async def test_nota_continua_consultavel_depois_de_cancelar(self, cliente, pronto) -> None:
        invoice_id = pronto["emissao"]["invoice_id"]
        await cliente.post(
            f"/v1/emissoes/{invoice_id}/cancelamento",
            json={"c_motivo": "2", "x_motivo": MOTIVO_OK},
            headers=pronto["cabecalho"],
        )
        consulta = await cliente.get(f"/v1/emissoes/{invoice_id}", headers=pronto["cabecalho"])
        assert consulta.status_code == 200
        # XML autorizado permanece: nota cancelada ainda precisa ser demonstrável.
        assert consulta.json()["documento"]["tem_xml_autorizado"] is True

    async def test_registra_evento_de_cancelamento(self, cliente, pronto, sessao_db) -> None:
        invoice_id = pronto["emissao"]["invoice_id"]
        await cliente.post(
            f"/v1/emissoes/{invoice_id}/cancelamento",
            json={"c_motivo": "1", "x_motivo": MOTIVO_OK},
            headers=pronto["cabecalho"],
        )
        eventos = (
            (
                await sessao_db.execute(
                    select(InvoiceEvent).where(InvoiceEvent.tipo == "cancelamento")
                )
            )
            .scalars()
            .all()
        )
        assert eventos
        evento = eventos[-1]
        assert evento.requisicao["c_motivo"] == "1"
        assert evento.requisicao["id_pedido"].startswith("PRE")
        assert evento.xml_evento and "<evento" in evento.xml_evento

    async def test_segundo_cancelamento_da_409(self, cliente, pronto) -> None:
        invoice_id = pronto["emissao"]["invoice_id"]
        primeira = await cliente.post(
            f"/v1/emissoes/{invoice_id}/cancelamento",
            json={"c_motivo": "1", "x_motivo": MOTIVO_OK},
            headers=pronto["cabecalho"],
        )
        assert primeira.status_code == 200
        segunda = await cliente.post(
            f"/v1/emissoes/{invoice_id}/cancelamento",
            json={"c_motivo": "1", "x_motivo": MOTIVO_OK},
            headers=pronto["cabecalho"],
        )
        assert segunda.status_code == 409

    async def test_motivo_invalido_da_422(self, cliente, pronto) -> None:
        invoice_id = pronto["emissao"]["invoice_id"]
        resposta = await cliente.post(
            f"/v1/emissoes/{invoice_id}/cancelamento",
            json={"c_motivo": "7", "x_motivo": MOTIVO_OK},
            headers=pronto["cabecalho"],
        )
        assert resposta.status_code == 422

    async def test_motivo_curto_da_422(self, cliente, pronto) -> None:
        invoice_id = pronto["emissao"]["invoice_id"]
        resposta = await cliente.post(
            f"/v1/emissoes/{invoice_id}/cancelamento",
            json={"c_motivo": "1", "x_motivo": "curto"},
            headers=pronto["cabecalho"],
        )
        assert resposta.status_code == 422, "schema exige 15 caracteres ou mais"

    async def test_emissao_inexistente_da_404(self, cliente, pronto) -> None:
        import uuid

        resposta = await cliente.post(
            f"/v1/emissoes/{uuid.uuid4()}/cancelamento",
            json={"c_motivo": "1", "x_motivo": MOTIVO_OK},
            headers=pronto["cabecalho"],
        )
        assert resposta.status_code == 404

    async def test_fatura_sem_documento_autorizado_da_409(self, cliente, pronto, sessao_db) -> None:
        """Cancelar fatura sem documento autorizado é 409, não 500.

        Só existe nota a cancelar se ela foi autorizada. Sem essa guarda, o código
        tentaria montar evento para chave inexistente e a SEFIN recusaria com
        código genérico — erro pior de diagnosticar.
        """
        from app.db.models.invoice import Invoice
        from app.db.models.tenant import Tenant
        from sqlalchemy import select

        tenant = (
            await sessao_db.execute(select(Tenant).where(Tenant.slug == "cancel-tenant"))
        ).scalar_one()
        fatura = Invoice(
            tenant_id=tenant.id,
            idempotency_key="cancel-sem-documento-001",
            status=StatusFatura.PENDENTE,
            valor_servico="50.00",
            descricao_servico="nunca autorizada",
        )
        sessao_db.add(fatura)
        await sessao_db.commit()

        resposta = await cliente.post(
            f"/v1/emissoes/{fatura.id}/cancelamento",
            json={"c_motivo": "1", "x_motivo": MOTIVO_OK},
            headers=pronto["cabecalho"],
        )
        assert resposta.status_code == 409
        assert "autorizado" in resposta.json()["detail"].lower()


class TestIsolamento:
    async def test_cancelar_de_outro_tenant_da_404(self, cliente, pronto) -> None:
        outro = await cliente.post(
            "/v1/tenants", json={"slug": "cancel-outro", "nome": "Outro LTDA"}
        )
        resposta = await cliente.post(
            f"/v1/emissoes/{pronto['emissao']['invoice_id']}/cancelamento",
            json={"c_motivo": "1", "x_motivo": MOTIVO_OK},
            headers={"X-API-Key": outro.json()["api_key"]},
        )
        assert resposta.status_code == 404
