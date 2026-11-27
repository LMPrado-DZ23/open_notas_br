"""Decisão de rota da NFS-e (§77).

Antes: `aderente_emissor_nacional` era gravado e **nunca consultado**. O sistema sempre tentava o
Emissor Nacional, e a rota errada só aparecia como rejeição `E0312` depois de gerar, assinar e
transmitir.

Estes testes cobrem cada ramo do módulo, com a fonte citada no próprio código:

- obrigação nacional do Simples a partir da competência 2026-11 (FAQ NFS-e v1.2/v1.3, consultada em
  2026-11-27);
- município não aderente com parâmetro **confirmado** → bloqueio com pendência;
- parâmetro **não confirmado** → aviso fora de produção, bloqueio em produção;
- **exceção de MEI e grupo 99 não implementada**: a alegação não foi confirmada em fonte oficial, e
  inventar a exceção produziria nota pela rota errada com aparência de autorizada.
"""

from __future__ import annotations

import pytest
from app.nfse.roteamento import DecisaoRota, decidir_rota


def _decidir(**over):
    base = {
        "aderente_emissor_nacional": False,
        "aderente_confirmado": True,
        "simples_nacional": False,
        "optante_mei": False,
        "competencia": "2026-11",
        "ambiente": "homologacao",
    }
    base.update(over)
    return decidir_rota(**base)


class TestObrigacaoNacional:
    def test_simples_a_partir_de_2026_11_passa_mesmo_sem_aderencia(self) -> None:
        decisao = _decidir(simples_nacional=True, competencia="2026-11")

        assert decisao.permitido is True
        assert decisao.rota == "nacional"
        assert decisao.confirmado is True
        assert "2026-11" in decisao.motivo

    def test_simples_antes_de_2026_11_nao_e_reclassificado(self) -> None:
        """Nota de competência anterior não ganha obrigação retroativa."""
        decisao = _decidir(simples_nacional=True, competencia="2026-10")

        assert decisao.permitido is False
        assert decisao.rota == "municipal"
        assert decisao.pendencia

    def test_mei_nao_recebe_tratamento_especial(self) -> None:
        """A exceção do MEI não foi confirmada em fonte oficial: comportamento é o conservador."""
        decisao = _decidir(simples_nacional=True, optante_mei=True, competencia="2026-11")

        assert decisao.permitido is False, (
            "MEI não pode escapar da regra sem fonte oficial que o sustente"
        )

    def test_competencia_ausente_nao_vira_obrigacao(self) -> None:
        decisao = _decidir(simples_nacional=True, competencia=None)

        assert decisao.permitido is False


class TestAderencia:
    def test_municipio_aderente_permite(self) -> None:
        decisao = _decidir(aderente_emissor_nacional=True)

        assert decisao.permitido is True
        assert decisao.confirmado is True

    def test_municipio_nao_aderente_bloqueia_com_pendencia(self) -> None:
        decisao = _decidir(aderente_emissor_nacional=False)

        assert decisao.permitido is False
        assert decisao.rota == "municipal"
        assert decisao.pendencia and "municipal" in decisao.pendencia


class TestParametroNaoConfirmado:
    def test_producao_exige_confirmacao(self) -> None:
        decisao = _decidir(aderente_confirmado=False, ambiente="producao")

        assert decisao.permitido is False
        assert decisao.rota == "indefinida"
        assert decisao.pendencia and "aderente_confirmado_em" in decisao.pendencia

    def test_homologacao_avisa_e_segue(self) -> None:
        """Fora de produção, não confirmar não pode impedir teste — mas não é prova de rota."""
        decisao = _decidir(aderente_confirmado=False, ambiente="homologacao")

        assert decisao.permitido is True
        assert decisao.confirmado is False
        assert "não confirmado" in decisao.motivo


class TestContrato:
    def test_decisao_e_imutavel(self) -> None:
        decisao = _decidir(aderente_emissor_nacional=True)

        assert isinstance(decisao, DecisaoRota)
        with pytest.raises((AttributeError, TypeError)):
            decisao.permitido = False  # type: ignore[misc]

    def test_bloqueio_sempre_traz_proximo_passo(self) -> None:
        for decisao in (
            _decidir(aderente_emissor_nacional=False),
            _decidir(aderente_confirmado=False, ambiente="producao"),
            _decidir(simples_nacional=True, competencia="2026-10"),
        ):
            assert decisao.permitido is False
            assert decisao.pendencia, "bloqueio sem pendência obriga o operador a adivinhar"


class TestPreflightNaRota:
    """O bloqueio acontece **na rota real**, antes de assinar e transmitir (§77).

    O teste unitário prova a decisão; este prova que a emissão para. Sem ele, o módulo poderia ficar
    correto e desconectado — exatamente o defeito que §59 documenta em outros módulos.
    """

    async def _preparar(self, cliente, sessao_db, slug: str, **config_extra):
        from app.db.models.tenant import Tenant, TenantFiscalConfig
        from sqlalchemy import select

        from tests.test_fase2_certificado import SENHA, gerar_pfx

        criado = await cliente.post("/v1/tenants", json={"slug": slug, "nome": f"{slug} LTDA"})
        tenant = criado.json()
        cabecalho = {"X-API-Key": tenant["api_key"]}
        payload = {
            "municipio_ibge": "5200258",
            "uf": "GO",
            "ambiente": "homologacao",
            "codigo_tributacao_nacional": "010701",
            "serie_dps": "1",
            "aliquota_iss": 0.05,
            "simples_nacional": False,
        }
        payload.update(config_extra)
        await cliente.put("/v1/me/config-fiscal", json=payload, headers=cabecalho)
        await cliente.post(
            "/v1/me/certificados",
            files={"arquivo": ("c.pfx", gerar_pfx(), "application/x-pkcs12")},
            data={"senha": SENHA.decode(), "apelido": "a1"},
            headers=cabecalho,
        )

        # Força o parâmetro "confirmado em fonte oficial" — é o que faz o bloqueio valer.
        registro = (await sessao_db.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one()
        config_reg = (
            await sessao_db.execute(
                select(TenantFiscalConfig).where(TenantFiscalConfig.tenant_id == registro.id)
            )
        ).scalar_one()
        if config_extra.get("confirmar", True):
            from datetime import UTC, datetime

            config_reg.aderente_confirmado_em = datetime.now(UTC)
            config_reg.aderente_fonte = "teste"
        await sessao_db.commit()
        return tenant

    async def test_municipio_nao_aderente_bloqueia_emissao(self, cliente, sessao_db) -> None:
        tenant = await self._preparar(cliente, sessao_db, "rota-bloq")

        resposta = await cliente.post(
            "/v1/emissoes",
            json={
                "idempotency_key": "rota-0001",
                "valor": "10.00",
                "descricao": "Servico",
                "competencia": "2026-10",
            },
            headers={"X-API-Key": tenant["api_key"]},
        )

        assert resposta.status_code == 422, resposta.text
        detalhe = resposta.json()["detail"]
        assert "não aderente" in detalhe or "nao aderente" in detalhe
        assert "Pendência" in detalhe

    async def test_simples_em_2026_11_passa(self, cliente, sessao_db) -> None:
        tenant = await self._preparar(cliente, sessao_db, "rota-simples", simples_nacional=True)

        resposta = await cliente.post(
            "/v1/emissoes",
            json={
                "idempotency_key": "rota-0002",
                "valor": "10.00",
                "descricao": "Servico",
                "competencia": "2026-11",
            },
            headers={"X-API-Key": tenant["api_key"]},
        )

        assert resposta.status_code == 201, resposta.text

    async def test_bloqueio_de_um_tenant_nao_afeta_outro(self, cliente, sessao_db) -> None:
        bloqueado = await self._preparar(cliente, sessao_db, "rota-x")
        liberado = await self._preparar(cliente, sessao_db, "rota-y", simples_nacional=True)

        negado = await cliente.post(
            "/v1/emissoes",
            json={
                "idempotency_key": "rota-0003",
                "valor": "10.00",
                "descricao": "Servico",
                "competencia": "2026-10",
            },
            headers={"X-API-Key": bloqueado["api_key"]},
        )
        aceito = await cliente.post(
            "/v1/emissoes",
            json={
                "idempotency_key": "rota-0004",
                "valor": "10.00",
                "descricao": "Servico",
                "competencia": "2026-11",
            },
            headers={"X-API-Key": liberado["api_key"]},
        )

        assert negado.status_code == 422
        assert aceito.status_code == 201, aceito.text
