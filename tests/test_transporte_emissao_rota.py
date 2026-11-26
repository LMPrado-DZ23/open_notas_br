"""`POST /v1/transportes/cte` e `/mdfe`: o caminho feliz que faltava (§25, §42).

Até aqui as rotas de emissão só tinham teste de auth e de OpenAPI. A lacuna estava declarada
em `tests/test_transporte_rotas.py` ("não é fingido aqui") — e declarar não é testar: foi
exatamente essa lacuna que escondeu o 500 da rota de status (§41).

O que este arquivo prova: tenant da API key → A1 do cofre → XML gerado, assinado e validado
contra o XSD oficial, devolvido como `application/xml`. **Nada é transmitido** ao autorizador.
"""

from __future__ import annotations

import base64
from uuid import UUID

import pytest
from lxml import etree

from tests.test_fase2_certificado import SENHA, gerar_pfx
from tests.test_transporte_schemas import TestMDFeIn, cte

NS_CTE = "http://www.portalfiscal.inf.br/cte"
NS_MDFE = "http://www.portalfiscal.inf.br/mdfe"
NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"


@pytest.fixture
async def ambiente_emissao(cliente, sessao_db):
    """Tenant com A1 ativo no cofre, e o PEM do mesmo A1 para conferência."""
    from app.certificates import service as certificados
    from app.certificates.cofre import CertificadoA1

    criado = await cliente.post("/v1/tenants", json={"slug": "emissao-a", "nome": "Emissao A"})
    assert criado.status_code == 201, criado.text
    corpo = criado.json()

    pfx = gerar_pfx()
    await certificados.registrar(
        sessao_db, UUID(corpo["id"]), apelido="a1", pfx=pfx, senha=SENHA.decode()
    )
    await sessao_db.commit()

    esperado = CertificadoA1.de_pfx(pfx, SENHA.decode())
    _, cadeia_pem = esperado.material_para_assinatura()
    certificado_der = base64.b64decode(
        "".join(cadeia_pem[0].splitlines()[1:-1])  # tira BEGIN/END do PEM
    )

    return {
        "cabecalho": {"X-API-Key": corpo["api_key"]},
        "cert_der": certificado_der,
    }


def _x509_do_xml(xml: bytes) -> bytes:
    """DER do `X509Certificate` embutido na assinatura."""
    raiz = etree.fromstring(xml)
    no = raiz.find(f".//{{{NS_DSIG}}}X509Certificate")
    assert no is not None and no.text, "assinatura sem X509Certificate"
    return base64.b64decode("".join(no.text.split()))


class TestCTe:
    async def test_devolve_xml_assinado(self, cliente, ambiente_emissao) -> None:
        resposta = await cliente.post(
            "/v1/transportes/cte",
            json=cte(data_emissao="2026-11-26T12:00:00"),
            headers=ambiente_emissao["cabecalho"],
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.headers["content-type"].startswith("application/xml")

        corpo = resposta.content
        assert b"Signature" in corpo, "sem assinatura o CT-e e invalido pelo schema"

        raiz = etree.fromstring(corpo)
        assert etree.QName(raiz).namespace == NS_CTE
        assert etree.QName(raiz).localname == "CTe"
        inf = raiz.find(f"{{{NS_CTE}}}infCte")
        assert inf is not None and inf.get("Id", "").startswith("CTe")

    async def test_assinatura_usa_o_certificado_do_tenant(self, cliente, ambiente_emissao) -> None:
        """O `X509Certificate` embutido é o DER do A1 do tenant — não um literal."""
        resposta = await cliente.post(
            "/v1/transportes/cte",
            json=cte(data_emissao="2026-11-26T12:00:00"),
            headers=ambiente_emissao["cabecalho"],
        )
        assert resposta.status_code == 200, resposta.text
        assert _x509_do_xml(resposta.content) == ambiente_emissao["cert_der"]

    async def test_sem_certificado_vira_422(self, cliente) -> None:
        criado = await cliente.post(
            "/v1/tenants", json={"slug": "emissao-sem-cert", "nome": "Sem Certificado"}
        )
        assert criado.status_code == 201, criado.text

        resposta = await cliente.post(
            "/v1/transportes/cte",
            json=cte(data_emissao="2026-11-26T12:00:00"),
            headers={"X-API-Key": criado.json()["api_key"]},
        )
        assert resposta.status_code == 422, resposta.text
        assert "certificado A1 ativo" in resposta.json()["detail"]


class TestMDFe:
    async def test_devolve_xml_assinado(self, cliente, ambiente_emissao) -> None:
        resposta = await cliente.post(
            "/v1/transportes/mdfe",
            json=TestMDFeIn().base(),
            headers=ambiente_emissao["cabecalho"],
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.headers["content-type"].startswith("application/xml")
        assert b"Signature" in resposta.content

        raiz = etree.fromstring(resposta.content)
        assert etree.QName(raiz).namespace == NS_MDFE
        assert etree.QName(raiz).localname == "MDFe"

    async def test_assinatura_usa_o_certificado_do_tenant(self, cliente, ambiente_emissao) -> None:
        resposta = await cliente.post(
            "/v1/transportes/mdfe",
            json=TestMDFeIn().base(),
            headers=ambiente_emissao["cabecalho"],
        )
        assert resposta.status_code == 200, resposta.text
        assert _x509_do_xml(resposta.content) == ambiente_emissao["cert_der"]
