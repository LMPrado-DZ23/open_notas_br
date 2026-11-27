"""Dois certificados ativos não podem virar escolha silenciosa (§80).

Antes: `ativo()` devolvia `.first()`. Com dois certificados ativos, a emissão **assinava com um ao
acaso** — e não há como detectar depois: a nota sai autorizada com o titular errado.

Agora: ambiguidade é erro declarado (409), com os certificados listados e a instrução de ativação.
A rota `/v1/me/certificados/{id}/ativar` já existe e desativa os demais — é o caminho de saída.
"""

from __future__ import annotations

from typing import Any

from tests.test_fase2_certificado import SENHA, gerar_pfx


def cabecalho(tenant: dict[str, Any]) -> dict[str, str]:
    return {"X-API-Key": tenant["api_key"]}


async def _tenant_pronto(cliente, slug: str) -> dict[str, Any]:
    criado = await cliente.post("/v1/tenants", json={"slug": slug, "nome": f"{slug} LTDA"})
    assert criado.status_code == 201, criado.text
    tenant = criado.json()
    await cliente.put(
        "/v1/me/config-fiscal",
        json={
            "municipio_ibge": "5200258",
            "uf": "GO",
            "ambiente": "homologacao",
            "codigo_tributacao_nacional": "010701",
            "serie_dps": "1",
            "aliquota_iss": 0.05,
        },
        headers=cabecalho(tenant),
    )
    primeiro = await cliente.post(
        "/v1/me/certificados",
        files={"arquivo": ("a.pfx", gerar_pfx(), "application/x-pkcs12")},
        data={"senha": SENHA.decode(), "apelido": "a1"},
        headers=cabecalho(tenant),
    )
    assert primeiro.status_code == 201, primeiro.text
    tenant["certificado_id"] = primeiro.json()["id"]
    return tenant


async def _forcar_segundo_ativo(cliente, tenant: dict[str, Any]) -> None:
    """Sobe um segundo A1 e o deixa ativo **sem** desativar o primeiro.

    O caminho normal (`/ativar`) desativa os demais; simular o estado quebrado exige gravar direto,
    porque é exatamente o estado que o banco permite e o código não previa.
    """
    segundo = await cliente.post(
        "/v1/me/certificados",
        files={"arquivo": ("b.pfx", gerar_pfx(), "application/x-pkcs12")},
        data={"senha": SENHA.decode(), "apelido": "a2"},
        headers=cabecalho(tenant),
    )
    assert segundo.status_code == 201, segundo.text
    tenant["segundo_id"] = segundo.json()["id"]


class TestAmbiguidade:
    async def test_dois_ativos_bloqueiam_emissao_com_409(self, cliente, sessao_db) -> None:
        from app.db.models.tenant import TenantCertificate
        from sqlalchemy import update

        tenant = await _tenant_pronto(cliente, "amb-1")
        await _forcar_segundo_ativo(cliente, tenant)

        # Estado quebrado: dois ativos no mesmo tenant.
        await sessao_db.execute(
            update(TenantCertificate)
            .where(TenantCertificate.tenant_id == tenant["id"])
            .values(ativo=True)
        )
        await sessao_db.commit()

        resposta = await cliente.post(
            "/v1/emissoes",
            json={"idempotency_key": "amb-0001", "valor": "10.00", "descricao": "Servico"},
            headers=cabecalho(tenant),
        )

        assert resposta.status_code == 409, resposta.text
        detalhe = resposta.json()["detail"]
        assert "mais de um certificado ativo" in detalhe
        assert "ativar" in detalhe

    async def test_ativar_um_resolve_a_ambiguidade(self, cliente, sessao_db) -> None:
        from app.db.models.tenant import TenantCertificate
        from sqlalchemy import update

        tenant = await _tenant_pronto(cliente, "amb-2")
        await _forcar_segundo_ativo(cliente, tenant)
        await sessao_db.execute(
            update(TenantCertificate)
            .where(TenantCertificate.tenant_id == tenant["id"])
            .values(ativo=True)
        )
        await sessao_db.commit()

        ativado = await cliente.post(
            f"/v1/me/certificados/{tenant['segundo_id']}/ativar", headers=cabecalho(tenant)
        )
        assert ativado.status_code == 200, ativado.text

        emitida = await cliente.post(
            "/v1/emissoes",
            json={"idempotency_key": "amb-0002", "valor": "10.00", "descricao": "Servico"},
            headers=cabecalho(tenant),
        )
        assert emitida.status_code == 201, emitida.text

    async def test_um_ativo_continua_emitindo(self, cliente) -> None:
        tenant = await _tenant_pronto(cliente, "amb-3")

        emitida = await cliente.post(
            "/v1/emissoes",
            json={"idempotency_key": "amb-0003", "valor": "10.00", "descricao": "Servico"},
            headers=cabecalho(tenant),
        )

        assert emitida.status_code == 201, emitida.text
