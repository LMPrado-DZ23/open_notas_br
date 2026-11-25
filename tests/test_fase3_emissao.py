"""Fluxo fim-a-fim: tenant → configuração → certificado → emissão.

Usa o dublê da SEFIN (`nfse_adapter=mock`) e um certificado A1 gerado no teste.
Isso exercita o caminho **completo**, incluindo assinatura XMLDSig real: a única
coisa simulada é a resposta da SEFIN. Sem certificado real e credenciamento, é o
máximo de verificação possível — e está declarado em `docs/ESCOPO.md`.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.core.config import Settings, get_settings

from tests.test_fase2_certificado import SENHA, gerar_pfx


@pytest.fixture
async def tenant(cliente) -> dict[str, Any]:
    resposta = await cliente.post(
        "/v1/tenants", json={"slug": "emissor-e2e", "nome": "Emissor E2E LTDA"}
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def cabecalho(tenant: dict[str, Any]) -> dict[str, str]:
    return {"X-API-Key": tenant["api_key"]}


async def configurar_fiscal(cliente, tenant: dict[str, Any]) -> None:
    resposta = await cliente.put(
        "/v1/me/config-fiscal",
        json={
            "municipio_ibge": "3550308",
            "municipio_nome": "São Paulo",
            "uf": "SP",
            "ambiente": "homologacao",
            "regime_tributario": 3,
            "simples_nacional": False,
            "codigo_tributacao_nacional": "010701",
            "serie_dps": "1",
            "aliquota_iss": 0.05,
        },
        headers=cabecalho(tenant),
    )
    assert resposta.status_code == 200, resposta.text


async def enviar_certificado(cliente, tenant: dict[str, Any]) -> dict[str, Any]:
    pfx = gerar_pfx()
    resposta = await cliente.post(
        "/v1/me/certificados",
        files={"arquivo": ("certificado.pfx", pfx, "application/x-pkcs12")},
        data={"senha": SENHA.decode(), "apelido": "certificado-teste"},
        headers=cabecalho(tenant),
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


@pytest.fixture
def adapter_mock(app_teste):
    """Força o dublê da SEFIN nas rotas."""
    base = Settings(environment="test", nfse_adapter="mock")
    app_teste.dependency_overrides[get_settings] = lambda: base
    yield
    app_teste.dependency_overrides.clear()


class TestUploadCertificado:
    async def test_upload_retorna_metadados_sem_pfx(self, cliente, tenant) -> None:
        dados = await enviar_certificado(cliente, tenant)

        assert dados["apelido"] == "certificado-teste"
        assert dados["cnpj"] == "11222333000181"
        assert dados["ativo"] is True
        assert dados["fingerprint_sha256"]
        assert dados["dias_restantes"] > 300
        texto = str(dados)
        assert "PRIVATE KEY" not in texto
        assert "pfx" not in texto.lower()

    async def test_mesmo_certificado_duas_vezes_da_409(self, cliente, tenant) -> None:
        pfx = gerar_pfx()
        primeiro = await cliente.post(
            "/v1/me/certificados",
            files={"arquivo": ("c.pfx", pfx, "application/x-pkcs12")},
            data={"senha": SENHA.decode(), "apelido": "a"},
            headers=cabecalho(tenant),
        )
        assert primeiro.status_code == 201

        segundo = await cliente.post(
            "/v1/me/certificados",
            files={"arquivo": ("c.pfx", pfx, "application/x-pkcs12")},
            data={"senha": SENHA.decode(), "apelido": "b"},
            headers=cabecalho(tenant),
        )
        assert segundo.status_code == 409

    async def test_senha_errada_da_422(self, cliente, tenant) -> None:
        resposta = await cliente.post(
            "/v1/me/certificados",
            files={"arquivo": ("c.pfx", gerar_pfx(), "application/x-pkcs12")},
            data={"senha": "senha-errada", "apelido": "x"},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 422
        assert "senha" in resposta.json()["detail"].lower()

    async def test_arquivo_que_nao_e_pfx_da_422(self, cliente, tenant) -> None:
        resposta = await cliente.post(
            "/v1/me/certificados",
            files={"arquivo": ("c.pfx", b"isto nao e pkcs12", "application/x-pkcs12")},
            data={"senha": "x", "apelido": "x"},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 422

    async def test_saude_sem_certificado(self, cliente, tenant) -> None:
        resposta = await cliente.get("/v1/me/certificados/saude", headers=cabecalho(tenant))
        assert resposta.status_code == 200
        assert resposta.json()["existe"] is False

    async def test_saude_com_certificado(self, cliente, tenant) -> None:
        await enviar_certificado(cliente, tenant)
        resposta = await cliente.get("/v1/me/certificados/saude", headers=cabecalho(tenant))
        corpo = resposta.json()
        assert corpo["existe"] is True
        assert corpo["expirado"] is False
        assert corpo["cnpj"] == "11222333000181"

    async def test_pfx_selado_no_banco_nao_contem_o_arquivo(
        self, cliente, tenant, sessao_db
    ) -> None:
        from app.db.models.tenant import TenantCertificate
        from sqlalchemy import select

        pfx = gerar_pfx()
        await cliente.post(
            "/v1/me/certificados",
            files={"arquivo": ("c.pfx", pfx, "application/x-pkcs12")},
            data={"senha": SENHA.decode(), "apelido": "selado"},
            headers=cabecalho(tenant),
        )

        resultado = await sessao_db.execute(
            select(TenantCertificate).where(TenantCertificate.apelido == "selado")
        )
        registro = resultado.scalar_one()
        assert pfx not in registro.pfx_selado
        assert pfx[:32] not in registro.pfx_selado

    async def test_isolamento_entre_tenants(self, cliente, tenant) -> None:
        outro = await cliente.post(
            "/v1/tenants", json={"slug": "outro-emissor", "nome": "Outro LTDA"}
        )
        outro_tenant = outro.json()

        dados = await enviar_certificado(cliente, tenant)

        listagem_outro = await cliente.get("/v1/me/certificados", headers=cabecalho(outro_tenant))
        assert listagem_outro.json() == []

        remocao = await cliente.delete(
            f"/v1/me/certificados/{dados['id']}", headers=cabecalho(outro_tenant)
        )
        assert remocao.status_code == 404


class TestEmissao:
    async def test_emissao_completa(self, cliente, tenant, adapter_mock) -> None:
        await configurar_fiscal(cliente, tenant)
        await enviar_certificado(cliente, tenant)

        resposta = await cliente.post(
            "/v1/emissoes",
            json={
                "idempotency_key": "venda-0001",
                "valor": "85.00",
                "descricao": "Corte de cabelo masculino",
                "tomador_nome": "Cliente Exemplo",
                "tomador_documento": "11144477735",
            },
            headers=cabecalho(tenant),
        )

        assert resposta.status_code == 201, resposta.text
        corpo = resposta.json()
        assert corpo["chave"], "a emissão deve devolver a chave da NFS-e"
        assert len(corpo["chave"]) == 50
        assert corpo["documento"]["tem_xml_autorizado"] is True
        assert corpo["ja_existia"] is False

    async def test_idempotencia_nao_duplica_nota(self, cliente, tenant, adapter_mock) -> None:
        await configurar_fiscal(cliente, tenant)
        await enviar_certificado(cliente, tenant)

        corpo = {
            "idempotency_key": "venda-repetida",
            "valor": "120.00",
            "descricao": "Barba e cabelo",
        }

        primeira = await cliente.post("/v1/emissoes", json=corpo, headers=cabecalho(tenant))
        segunda = await cliente.post("/v1/emissoes", json=corpo, headers=cabecalho(tenant))

        assert primeira.status_code == 201
        assert segunda.status_code == 200
        assert segunda.json()["ja_existia"] is True
        assert segunda.json()["chave"] == primeira.json()["chave"]
        assert segunda.json()["invoice_id"] == primeira.json()["invoice_id"]

    async def test_sem_certificado_da_422(self, cliente, tenant, adapter_mock) -> None:
        await configurar_fiscal(cliente, tenant)

        resposta = await cliente.post(
            "/v1/emissoes",
            json={"idempotency_key": "sem-cert", "valor": "10.00", "descricao": "Serviço"},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 422
        assert "certificado" in resposta.json()["detail"].lower()

    async def test_sem_configuracao_fiscal_da_422(self, cliente, tenant, adapter_mock) -> None:
        await enviar_certificado(cliente, tenant)

        resposta = await cliente.post(
            "/v1/emissoes",
            json={"idempotency_key": "sem-config", "valor": "10.00", "descricao": "Serviço"},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 422
        assert "configuração fiscal" in resposta.json()["detail"].lower()

    async def test_consulta_traz_xml_autorizado(self, cliente, tenant, adapter_mock) -> None:
        await configurar_fiscal(cliente, tenant)
        await enviar_certificado(cliente, tenant)

        criada = await cliente.post(
            "/v1/emissoes",
            json={"idempotency_key": "consulta-1", "valor": "50.00", "descricao": "Serviço X"},
            headers=cabecalho(tenant),
        )
        assert criada.status_code == 201, criada.text
        invoice_id = criada.json()["invoice_id"]

        consulta = await cliente.get(f"/v1/emissoes/{invoice_id}", headers=cabecalho(tenant))
        assert consulta.status_code == 200
        corpo = consulta.json()
        assert corpo["xml_autorizado"]
        assert "NFSe" in corpo["xml_autorizado"]

    async def test_listagem_por_tenant(self, cliente, tenant, adapter_mock) -> None:
        await configurar_fiscal(cliente, tenant)
        await enviar_certificado(cliente, tenant)

        for indice in range(3):
            await cliente.post(
                "/v1/emissoes",
                json={
                    "idempotency_key": f"lote-{indice}-completo",
                    "valor": "10.00",
                    "descricao": f"Serviço {indice}",
                },
                headers=cabecalho(tenant),
            )

        listagem = await cliente.get("/v1/emissoes", headers=cabecalho(tenant))
        assert listagem.status_code == 200
        assert len(listagem.json()) == 3

    async def test_emissao_de_outro_tenant_nao_e_visivel(
        self, cliente, tenant, adapter_mock
    ) -> None:
        await configurar_fiscal(cliente, tenant)
        await enviar_certificado(cliente, tenant)
        criada = await cliente.post(
            "/v1/emissoes",
            json={"idempotency_key": "chave-privada", "valor": "10.00", "descricao": "Serviço"},
            headers=cabecalho(tenant),
        )
        assert criada.status_code == 201, criada.text
        invoice_id = criada.json()["invoice_id"]

        outro = await cliente.post(
            "/v1/tenants", json={"slug": "espectador", "nome": "Espectador LTDA"}
        )
        consulta = await cliente.get(f"/v1/emissoes/{invoice_id}", headers=cabecalho(outro.json()))
        assert consulta.status_code == 404

    async def test_evento_de_autorizacao_registrado(
        self, cliente, tenant, adapter_mock, sessao_db
    ) -> None:
        from app.db.models.invoice import InvoiceEvent
        from sqlalchemy import select

        await configurar_fiscal(cliente, tenant)
        await enviar_certificado(cliente, tenant)
        await cliente.post(
            "/v1/emissoes",
            json={"idempotency_key": "com-evento", "valor": "10.00", "descricao": "Serviço"},
            headers=cabecalho(tenant),
        )

        resultado = await sessao_db.execute(
            select(InvoiceEvent).where(InvoiceEvent.tipo == "autorizada")
        )
        evento = resultado.scalars().first()
        assert evento is not None
        assert evento.status == "autorizado"

    async def test_numero_da_dps_avanca(self, cliente, tenant, adapter_mock, sessao_db) -> None:
        from app.db.models.tenant import TenantFiscalConfig
        from sqlalchemy import select

        await configurar_fiscal(cliente, tenant)
        await enviar_certificado(cliente, tenant)

        for indice in range(2):
            await cliente.post(
                "/v1/emissoes",
                json={
                    "idempotency_key": f"sequencia-{indice}",
                    "valor": "10.00",
                    "descricao": "Serviço",
                },
                headers=cabecalho(tenant),
            )

        resultado = await sessao_db.execute(
            select(TenantFiscalConfig).where(
                TenantFiscalConfig.tenant_id == uuid.UUID(tenant["id"])
            )
        )
        config = resultado.scalars().first()
        assert config is not None
        assert config.proximo_numero_dps >= 3, "cada emissão consome um número de DPS"
