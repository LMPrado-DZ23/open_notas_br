"""Status de transporte na API: auth, catálogo, recusas e caminho feliz.

O caminho feliz **não** chama a SEFAZ: o cliente SOAP é substituído por um duplo que
devolve um `retConsStatServCTe`/`retConsStatMDFe` sintético. O que este arquivo prova é o
contrato HTTP da rota (catálogo → certificado → transporte → `cStat`/`xMotivo`, com os
códigos 200/422/503/504). Chamada real ao autorizador está medida na auditoria (§31), não
aqui — teste de rede não é teste de contrato.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from lxml import etree

NS_CTE = "http://www.portalfiscal.inf.br/cte"
NS_MDFE = "http://www.portalfiscal.inf.br/mdfe"


def _resposta(ns: str, raiz: str, cstat: str, motivo: str):
    """Resposta do autorizador no formato que `RespostaSefaz` consome."""
    from app.nfe.transporte import RespostaSefaz

    xml = f'<{raiz} xmlns="{ns}"><cStat>{cstat}</cStat><xMotivo>{motivo}</xMotivo></{raiz}>'
    elemento = etree.fromstring(xml.encode("utf-8"))
    return RespostaSefaz(xml=xml.encode("utf-8"), elemento=elemento)


@pytest.fixture
async def ambiente_status(cliente, sessao_db):
    """Tenant com A1 ativo + endpoint de status de CT-e no catálogo."""
    from app.certificates import service as certificados
    from app.db.models.webservice_sefaz import ServicoSefaz, WebserviceSefaz

    from tests.test_fase2_certificado import SENHA, gerar_pfx

    criado = await cliente.post("/v1/tenants", json={"slug": "status-a", "nome": "Status A"})
    assert criado.status_code == 201, criado.text
    corpo = criado.json()

    await certificados.registrar(
        sessao_db, UUID(corpo["id"]), apelido="a1", pfx=gerar_pfx(), senha=SENHA.decode()
    )
    sessao_db.add(
        WebserviceSefaz(
            uf="ES",
            ambiente="2",
            servico=ServicoSefaz.CTE_STATUS,
            url="https://cte-homologacao.svrs.rs.gov.br/ws/CTeStatusServicoV4/CTeStatusServicoV4.asmx",
            fonte_url="https://www.cte.fazenda.gov.br/portal/webservices.aspx",
            modelo="57",
            autorizador="SVRS",
        )
    )
    sessao_db.add(
        WebserviceSefaz(
            uf="ES",
            ambiente="2",
            servico=ServicoSefaz.MDFE_STATUS,
            url="https://mdfe-homologacao.svrs.rs.gov.br/ws/MDFeStatusServico/MDFeStatusServico.asmx",
            fonte_url="https://www.mdfe.fazenda.gov.br/portal/webservices.aspx",
            modelo="58",
            autorizador="SVRS",
        )
    )
    await sessao_db.commit()

    return {"cabecalho": {"X-API-Key": corpo["api_key"]}}


class TestContrato:
    async def test_sem_api_key_recusa(self, cliente) -> None:
        resposta = await cliente.get("/v1/transportes/status?documento=cte&uf=ES")
        assert resposta.status_code in (401, 403), resposta.text

    def test_rota_existe_no_openapi(self) -> None:
        from app.main import criar_app

        assert "/v1/transportes/status" in criar_app().openapi()["paths"]

    def test_summary_diz_que_nao_emite(self) -> None:
        from app.main import criar_app

        resumo = criar_app().openapi()["paths"]["/v1/transportes/status"]["get"]["summary"]
        assert "não emite" in resumo

    def test_uf_desconhecida_vira_422(self) -> None:
        # A auth roda antes da validação de query, então o 422 de UF é testado na função que o
        # produz — sem depender de tenant no banco.
        from app.api.v1.transportes_status import _cuf
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            _cuf("XX")
        assert exc.value.status_code == 422

    def test_uf_conhecida_vira_codigo_ibge(self) -> None:
        from app.api.v1.transportes_status import _cuf

        assert _cuf("ES") == "32"
        assert _cuf("go") == "52"


class TestCaminhoFeliz:
    """200: catálogo → certificado → transporte → `cStat`/`xMotivo`."""

    async def test_cte_devolve_cstat_e_motivo(self, cliente, ambiente_status, monkeypatch) -> None:
        from app.api.v1 import transportes_status

        chamadas: list[dict[str, str]] = []

        async def falso(sefaz, *, url, cuf, ambiente):
            chamadas.append({"url": url, "cuf": cuf, "ambiente": ambiente})
            return _resposta(NS_CTE, "retConsStatServCTe", "107", "Servico em Operacao")

        monkeypatch.setattr(transportes_status.cte_consulta, "consultar_status", falso)

        resposta = await cliente.get(
            "/v1/transportes/status?documento=cte&uf=ES",
            headers=ambiente_status["cabecalho"],
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.json() == {
            "documento": "cte",
            "uf": "ES",
            "cstat": "107",
            "motivo": "Servico em Operacao",
        }
        # A URL vem do catálogo e o cUF é derivado da UF — não há literal no código.
        assert chamadas == [
            {
                "url": (
                    "https://cte-homologacao.svrs.rs.gov.br/ws/"
                    "CTeStatusServicoV4/CTeStatusServicoV4.asmx"
                ),
                "cuf": "32",
                "ambiente": "2",
            }
        ]

    async def test_mdfe_nao_envia_cuf(self, cliente, ambiente_status, monkeypatch) -> None:
        """O `consStatServMDFe` não tem `cUF`: a rota não pode inventar o campo."""
        from app.api.v1 import transportes_status

        recebido: dict[str, object] = {}

        async def falso(sefaz, *, url, ambiente):
            recebido.update({"url": url, "ambiente": ambiente})
            return _resposta(NS_MDFE, "retConsStatServMDFe", "107", "Servico em Operacao")

        monkeypatch.setattr(transportes_status.mdfe_consulta, "consultar_status", falso)

        resposta = await cliente.get(
            "/v1/transportes/status?documento=mdfe&uf=ES",
            headers=ambiente_status["cabecalho"],
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["documento"] == "mdfe"
        assert recebido["ambiente"] == "2"


class TestRecusas:
    """503 sem catálogo, 422 sem certificado, 504 quando o autorizador falha."""

    async def test_sem_endpoint_no_catalogo_vira_503(self, cliente, ambiente_status) -> None:
        # ES tem catálogo; AC não. Catálogo incompleto é indisponibilidade, não erro do cliente.
        resposta = await cliente.get(
            "/v1/transportes/status?documento=cte&uf=AC",
            headers=ambiente_status["cabecalho"],
        )
        assert resposta.status_code == 503, resposta.text
        assert "sem endpoint de status de CTE para AC" in resposta.json()["detail"]

    async def test_tenant_sem_certificado_vira_422(self, cliente, ambiente_status) -> None:
        criado = await cliente.post(
            "/v1/tenants", json={"slug": "status-sem-cert", "nome": "Sem Certificado"}
        )
        assert criado.status_code == 201, criado.text

        resposta = await cliente.get(
            "/v1/transportes/status?documento=cte&uf=ES",
            headers={"X-API-Key": criado.json()["api_key"]},
        )
        assert resposta.status_code == 422, resposta.text
        assert "certificado A1 ativo" in resposta.json()["detail"]

    async def test_rejeicao_definitiva_vira_504(
        self, cliente, ambiente_status, monkeypatch
    ) -> None:
        from app.api.v1 import transportes_status
        from app.nfe.transporte import ErroSefazDefinitivo

        async def falso(sefaz, *, url, cuf, ambiente):
            raise ErroSefazDefinitivo("243: XML Mal Formado")

        monkeypatch.setattr(transportes_status.cte_consulta, "consultar_status", falso)

        resposta = await cliente.get(
            "/v1/transportes/status?documento=cte&uf=ES",
            headers=ambiente_status["cabecalho"],
        )
        assert resposta.status_code == 504, resposta.text
        assert "243" in resposta.json()["detail"]

    async def test_autorizador_inacessivel_vira_504(
        self, cliente, ambiente_status, monkeypatch
    ) -> None:
        from app.api.v1 import transportes_status
        from app.nfe.transporte import ErroTransporte

        async def falso(sefaz, *, url, cuf, ambiente):
            raise ErroTransporte("timeout")

        monkeypatch.setattr(transportes_status.cte_consulta, "consultar_status", falso)

        resposta = await cliente.get(
            "/v1/transportes/status?documento=cte&uf=ES",
            headers=ambiente_status["cabecalho"],
        )
        assert resposta.status_code == 504, resposta.text
        assert "inacessível" in resposta.json()["detail"]
