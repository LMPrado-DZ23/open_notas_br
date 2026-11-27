"""Escopos por chave de API (§75).

Antes: a chave era tudo-ou-nada no tenant. Não havia como dar só leitura ao ERP e só emissão ao PDV,
que é o caso real de integração.

Regra aplicada: `GET`/`HEAD`/`OPTIONS` exigem `leitura`; o resto exige `emissao`.
**Sem escopo (`None`) = sem restrição** — é o que mantém chave antiga funcionando.
"""

from __future__ import annotations

from typing import Any

from tests.test_fase2_certificado import SENHA, gerar_pfx


def cabecalho(chave: str) -> dict[str, str]:
    return {"X-API-Key": chave}


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
        headers=cabecalho(tenant["api_key"]),
    )
    # Emissão exige A1 ativo; o cenário de escopo precisa de uma emissão que PASSE para provar o
    # contrário (barrada por escopo, não por falta de certificado).
    certificado = await cliente.post(
        "/v1/me/certificados",
        files={"arquivo": ("c.pfx", gerar_pfx(), "application/x-pkcs12")},
        data={"senha": SENHA.decode(), "apelido": "a1"},
        headers=cabecalho(tenant["api_key"]),
    )
    assert certificado.status_code == 201, certificado.text
    return tenant


async def _rotacionar(cliente, chave: str, **corpo) -> dict[str, Any]:
    resposta = await cliente.post("/v1/me/rotacionar-chave", json=corpo, headers=cabecalho(chave))
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


class TestCompatibilidade:
    async def test_chave_sem_escopo_continua_com_tudo(self, cliente) -> None:
        """A ausência de escopo não pode virar ausência de acesso."""
        tenant = await _preparar(cliente, "esc-compat")

        leitura = await cliente.get("/v1/me", headers=cabecalho(tenant["api_key"]))
        escrita = await cliente.put(
            "/v1/me/config-fiscal",
            json={
                "municipio_ibge": "3550308",
                "uf": "SP",
                "ambiente": "homologacao",
                "codigo_tributacao_nacional": "010701",
                "serie_dps": "1",
                "aliquota_iss": 0.05,
            },
            headers=cabecalho(tenant["api_key"]),
        )

        assert leitura.status_code == 200
        assert escrita.status_code == 200
        assert leitura.status_code == 200


class TestEscopoDeLeitura:
    async def test_leitura_passa_emissao_e_barrada(self, cliente) -> None:
        tenant = await _preparar(cliente, "esc-leitura")
        nova = await _rotacionar(cliente, tenant["api_key"], escopos=["leitura"])
        chave = nova["api_key"]

        assert nova["api_key_escopos"] == ["leitura"]

        leitura = await cliente.get("/v1/me", headers=cabecalho(chave))
        escrita = await cliente.post(
            "/v1/emissoes",
            json={"idempotency_key": "esc-0001", "valor": "10.00", "descricao": "Servico"},
            headers=cabecalho(chave),
        )

        assert leitura.status_code == 200
        assert escrita.status_code == 403
        assert "emissao" in escrita.json()["detail"]

    async def test_a_chave_anterior_deixa_de_valer(self, cliente) -> None:
        tenant = await _preparar(cliente, "esc-antiga")
        await _rotacionar(cliente, tenant["api_key"], escopos=["leitura"])

        antiga = await cliente.get("/v1/me", headers=cabecalho(tenant["api_key"]))

        assert antiga.status_code == 401


class TestEscopoDeEmissao:
    async def test_emissao_passa_leitura_e_barra(self, cliente) -> None:
        tenant = await _preparar(cliente, "esc-emissao")
        nova = await _rotacionar(cliente, tenant["api_key"], escopos=["emissao"])
        chave = nova["api_key"]

        emissao = await cliente.post(
            "/v1/emissoes",
            json={"idempotency_key": "esc-0002", "valor": "10.00", "descricao": "Servico"},
            headers=cabecalho(chave),
        )
        leitura = await cliente.get("/v1/me", headers=cabecalho(chave))

        assert emissao.status_code == 201, emissao.text
        assert leitura.status_code == 403
        assert "leitura" in leitura.json()["detail"]


class TestPrazoEEscopo:
    async def test_prazo_e_escopo_juntos(self, cliente) -> None:
        tenant = await _preparar(cliente, "esc-prazo")

        nova = await _rotacionar(cliente, tenant["api_key"], dias_validade=30, escopos=["leitura"])

        assert nova["api_key_expira_em"] is not None
        assert nova["api_key_escopos"] == ["leitura"]

    async def test_escopo_invalido_e_recusado_no_contrato(self, cliente) -> None:
        tenant = await _preparar(cliente, "esc-invalido")

        resposta = await cliente.post(
            "/v1/me/rotacionar-chave",
            json={"escopos": ["admin"]},
            headers=cabecalho(tenant["api_key"]),
        )

        assert resposta.status_code == 422
