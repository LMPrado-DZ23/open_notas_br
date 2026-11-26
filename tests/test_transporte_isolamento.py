"""Rotas de CT-e e MDF-e: caminho feliz e isolamento entre tenants.

Passo 4 da exposição na API (auditoria §25). Prova o que os testes de contrato não provam:

- com certificado ativo, a rota devolve XML **assinado** (não só 200);
- sem certificado, recusa com 422 acionável;
- o certificado é **por tenant**: um tenant com certificado não empresta assinatura para outro.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from tests.test_fase2_certificado import SENHA, gerar_pfx

CHAVE = "52" + "0" * 42
CHAVE_DOC = "52" + "1" * 42


@pytest.fixture
async def ambiente(cliente, app_teste):
    """Sem override de `get_settings`.

    O upload do certificado e a assinatura precisam derivar a **mesma** chave do cofre. Override
    com um `Settings` novo faz o upload selar com uma chave e a leitura abrir com outra, e o
    erro aparece como `ErroDeCriptografia` — enganoso, porque a chave está certa; o que muda é
    qual instância de configuração cada lado enxerga. Os testes de emissão existentes seguem o
    mesmo caminho: configuração real do ambiente de teste, sem override.
    """
    yield


def cabecalho(tenant: dict[str, Any]) -> dict[str, str]:
    return {"X-API-Key": tenant["api_key"]}


async def criar_tenant(cliente, slug: str) -> dict[str, Any]:
    resposta = await cliente.post("/v1/tenants", json={"slug": slug, "nome": slug})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


async def enviar_certificado(cliente, tenant: dict[str, Any]) -> None:
    resposta = await cliente.post(
        "/v1/me/certificados",
        files={"arquivo": ("certificado.pfx", gerar_pfx(), "application/x-pkcs12")},
        data={"senha": SENHA.decode(), "apelido": "certificado-teste"},
        headers=cabecalho(tenant),
    )
    assert resposta.status_code == 201, resposta.text


def parte(nome: str) -> dict[str, Any]:
    return {
        "nome": nome,
        "cnpj": "11222333000181",
        "ie": "123456789",
        "municipio_ibge": "5208707",
        "municipio": "GOIANIA",
        "uf": "GO",
    }


def payload_cte() -> dict[str, Any]:
    return {
        "numero": 1,
        "serie": 1,
        "chave": CHAVE,
        "emitente": parte("EMPRESA TESTE"),
        "destinatario": parte("DESTINO TESTE"),
        "papel_tomador": "3",
        "valor_total": "100.00",
        "peso": "10.00",
        "produto": "CARGA",
        "data_emissao": datetime(2026, 11, 26, 12, 0).isoformat(),
        "rntrc": "12345678",
        "chaves_documentos": [CHAVE_DOC],
    }


def payload_mdfe() -> dict[str, Any]:
    return {
        "numero": 1,
        "serie": 1,
        "chave": CHAVE,
        "emitente": {
            "cnpj": "11222333000181",
            "nome": "EMPRESA TESTE",
            "ie": "123456789",
            "municipio_ibge": "5208707",
            "municipio": "GOIANIA",
            "uf": "GO",
        },
        "uf_inicio": "GO",
        "uf_fim": "GO",
        "municipios_carregamento": [{"codigo_ibge": "5208707", "nome": "GOIANIA"}],
        "valor_carga": "1000.00",
        "peso": "10.00",
        "data_emissao": datetime(2026, 11, 26, 12, 0).isoformat(),
        "descargas": [{"codigo_ibge": "5208707", "nome": "GOIANIA", "chaves_nfe": [CHAVE_DOC]}],
    }


class TestCaminhoFeliz:
    async def test_cte_com_certificado_devolve_xml_assinado(self, cliente, ambiente) -> None:
        tenant = await criar_tenant(cliente, "transportador-a")
        await enviar_certificado(cliente, tenant)

        resposta = await cliente.post(
            "/v1/transportes/cte", json=payload_cte(), headers=cabecalho(tenant)
        )
        assert resposta.status_code == 200, resposta.text
        assert b"<Signature" in resposta.content
        assert b"<CTe" in resposta.content

    async def test_mdfe_com_certificado_devolve_xml_assinado(self, cliente, ambiente) -> None:
        tenant = await criar_tenant(cliente, "transportador-mdfe")
        await enviar_certificado(cliente, tenant)

        resposta = await cliente.post(
            "/v1/transportes/mdfe", json=payload_mdfe(), headers=cabecalho(tenant)
        )
        assert resposta.status_code == 200, resposta.text
        assert b"<Signature" in resposta.content
        assert b"<MDFe" in resposta.content


class TestRecusaSemCertificado:
    async def test_cte_sem_certificado_e_422_acionavel(self, cliente, ambiente) -> None:
        tenant = await criar_tenant(cliente, "sem-certificado")
        resposta = await cliente.post(
            "/v1/transportes/cte", json=payload_cte(), headers=cabecalho(tenant)
        )
        assert resposta.status_code == 422, resposta.text
        assert "certificado" in resposta.json()["detail"].lower()
        # A mensagem precisa dizer onde resolver, senão o cliente fica sem saída.
        assert "/v1/me/certificados" in resposta.json()["detail"]


class TestIsolamentoEntreTenants:
    async def test_certificado_nao_e_emprestado(self, cliente, ambiente) -> None:
        """Tenant A tem certificado; tenant B não. B não pode assinar com o de A."""
        tenant_a = await criar_tenant(cliente, "transportador-com-cert")
        await enviar_certificado(cliente, tenant_a)
        tenant_b = await criar_tenant(cliente, "transportador-sem-cert")

        resposta_a = await cliente.post(
            "/v1/transportes/cte", json=payload_cte(), headers=cabecalho(tenant_a)
        )
        assert resposta_a.status_code == 200, resposta_a.text

        resposta_b = await cliente.post(
            "/v1/transportes/cte", json=payload_cte(), headers=cabecalho(tenant_b)
        )
        assert resposta_b.status_code == 422, resposta_b.text
        assert b"Signature" not in resposta_b.content
