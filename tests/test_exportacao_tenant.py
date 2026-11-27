"""Exportação dos dados do tenant (§76).

Adendo §6 item 10: portabilidade e exportação. O que precisa ser provado:

1. o pacote traz os dados do tenant autenticado;
2. **não** vaza nada de outro tenant;
3. **não** traz segredo (PFX, senha, hash de chave, segredo de webhook) mesmo quando existe;
4. XML fica fora por padrão e entra quando pedido, respeitando o limite.
"""

from __future__ import annotations

from typing import Any

from tests.test_fase2_certificado import SENHA, gerar_pfx


def cabecalho(tenant: dict[str, Any]) -> dict[str, str]:
    return {"X-API-Key": tenant["api_key"]}


async def _preparar(cliente, slug: str) -> dict[str, Any]:
    criado = await cliente.post("/v1/tenants", json={"slug": slug, "nome": f"{slug} LTDA"})
    assert criado.status_code == 201, criado.text
    tenant = criado.json()
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
    await cliente.post(
        "/v1/me/webhook",
        json={"url": "https://cliente.test/hook"},
        headers=cabecalho(tenant),
    )
    return tenant


class TestConteudo:
    async def test_exporta_dados_do_proprio_tenant(self, cliente) -> None:
        tenant = await _preparar(cliente, "exp-1")

        resposta = await cliente.get("/v1/me/exportacao", headers=cabecalho(tenant))

        assert resposta.status_code == 200, resposta.text
        pacote = resposta.json()
        assert pacote["tenant"]["slug"] == "exp-1"
        assert pacote["configuracao_fiscal"]["uf"] == "SP"
        assert len(pacote["certificados"]) == 1
        assert pacote["webhook"]["url"] == "https://cliente.test/hook"
        assert "emissoes_por_status" in pacote

    async def test_sem_xml_por_padrao(self, cliente) -> None:
        tenant = await _preparar(cliente, "exp-2")

        pacote = (await cliente.get("/v1/me/exportacao", headers=cabecalho(tenant))).json()

        assert "documentos" not in pacote


class TestNaoVazaSegredo:
    async def test_nenhum_segredo_no_pacote(self, cliente) -> None:
        tenant = await _preparar(cliente, "exp-3")

        corpo = (await cliente.get("/v1/me/exportacao", headers=cabecalho(tenant))).text.lower()

        for proibido in (
            "pfx_selado",
            "senha_selada",
            "api_key_hash",
            "webhook_secret",
            "signature",
        ):
            assert proibido not in corpo, f"segredo exportado: {proibido}"

    async def test_chave_de_api_nao_aparece(self, cliente) -> None:
        tenant = await _preparar(cliente, "exp-4")

        corpo = (await cliente.get("/v1/me/exportacao", headers=cabecalho(tenant))).text

        assert tenant["api_key"] not in corpo


class TestIsolamento:
    async def test_exportacao_nao_traz_dado_de_outro_tenant(self, cliente) -> None:
        um = await _preparar(cliente, "exp-5")
        outro = await _preparar(cliente, "exp-6")

        pacote = (await cliente.get("/v1/me/exportacao", headers=cabecalho(outro))).json()

        assert pacote["tenant"]["slug"] == "exp-6"
        assert um["id"] != outro["id"]
        assert all(c["id"] != um["id"] for c in pacote["certificados"])


class TestXmlSobDemanda:
    async def test_xml_entra_quando_pedido(self, cliente) -> None:
        tenant = await _preparar(cliente, "exp-7")
        await cliente.post(
            "/v1/emissoes",
            json={"idempotency_key": "exp-0001", "valor": "10.00", "descricao": "Servico"},
            headers=cabecalho(tenant),
        )

        pacote = (
            await cliente.get(
                "/v1/me/exportacao?incluir_xml=true&limite=10", headers=cabecalho(tenant)
            )
        ).json()

        assert "documentos" in pacote
        assert pacote["documentos_limite"] == 10
        assert pacote["documentos"], "emissão feita deveria aparecer no pacote"
