"""Ramos de borda e de recusa das rotas de ``app/api/v1``.

A suíte já provava os caminhos felizes. Este arquivo cobre o que faltava e que não é
cosmético: **qual status sai** quando o pré-requisito falta, quando o dado é inválido,
quando o registro de representações falha e quando a credencial foi revogada.

Regra do arquivo: toda asserção é sobre status e corpo. Onde o ramo é defesa em
profundidade (uma exceção que o schema de entrada já impede), o teste injeta a falha
de forma explícita e o docstring diz que está provando a **tradução** da exceção para
HTTP — não o caminho real. Nada aqui usa rede: emissão roda com o dublê do conftest.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import pytest
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from tests.construir import nfe
from tests.test_danfse import NFSE_XML
from tests.test_fase2_certificado import SENHA, gerar_pfx
from tests.test_transporte_isolamento import payload_cte as cte_base
from tests.test_transporte_isolamento import payload_mdfe as mdfe_base


def cabecalho(tenant: dict[str, Any]) -> dict[str, str]:
    return {"X-API-Key": tenant["api_key"]}


async def criar_tenant(cliente, slug: str) -> dict[str, Any]:
    resposta = await cliente.post("/v1/tenants", json={"slug": slug, "nome": f"{slug} LTDA"})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


async def configurar_fiscal(cliente, tenant: dict[str, Any]) -> None:
    resposta = await cliente.put(
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
    assert resposta.status_code == 200, resposta.text


async def enviar_certificado(cliente, tenant: dict[str, Any]) -> None:
    resposta = await cliente.post(
        "/v1/me/certificados",
        files={"arquivo": ("certificado.pfx", gerar_pfx(), "application/x-pkcs12")},
        data={"senha": SENHA.decode(), "apelido": "a1"},
        headers=cabecalho(tenant),
    )
    assert resposta.status_code == 201, resposta.text


async def tenant_que_pode_emitir(cliente, slug: str) -> dict[str, Any]:
    """Tenant com config fiscal e A1 no cofre: o mínimo para chegar ao gerador."""
    tenant = await criar_tenant(cliente, slug)
    await configurar_fiscal(cliente, tenant)
    await enviar_certificado(cliente, tenant)
    return tenant


# ---------------------------------------------------------------------------
# transportes.py — recusas do CT-e/MDF-e que não são 500
# ---------------------------------------------------------------------------
class TestTransportesRecusas:
    async def test_cte_sem_documento_nas_partes_e_422(self, cliente) -> None:
        """Payload válido na borda, inválido no domínio: 422 com o motivo do gerador."""
        tenant = await tenant_que_pode_emitir(cliente, "cte-sem-documento")
        payload = cte_base()
        # `ParteIn` aceita CNPJ ou CPF ausentes; quem recusa é o gerador. A rota
        # precisa traduzir essa recusa em 422, não deixar virar 500.
        payload["emitente"] = {
            "nome": "EMPRESA TESTE",
            "municipio_ibge": "5208707",
            "municipio": "GOIANIA",
            "uf": "GO",
        }

        resposta = await cliente.post(
            "/v1/transportes/cte", json=payload, headers=cabecalho(tenant)
        )

        assert resposta.status_code == 422, resposta.text
        assert "CNPJ nem CPF" in resposta.json()["detail"]

    async def test_cte_recusado_pelo_schema_e_422(self, cliente) -> None:
        """XML que o XSD oficial recusa sai como 422 (erro do cliente), não 500."""
        tenant = await tenant_que_pode_emitir(cliente, "cte-uf-invalida")
        payload = cte_base()
        payload["emitente"]["uf"] = "XX"
        payload["destinatario"]["uf"] = "XX"

        resposta = await cliente.post(
            "/v1/transportes/cte", json=payload, headers=cabecalho(tenant)
        )

        assert resposta.status_code == 422, resposta.text
        assert "CT-e" in resposta.json()["detail"]

    async def test_mdfe_recusado_pelo_schema_e_422(self, cliente) -> None:
        tenant = await tenant_que_pode_emitir(cliente, "mdfe-uf-invalida")
        payload = mdfe_base()
        payload["uf_inicio"] = "XX"
        payload["uf_fim"] = "XX"

        resposta = await cliente.post(
            "/v1/transportes/mdfe", json=payload, headers=cabecalho(tenant)
        )

        assert resposta.status_code == 422, resposta.text
        assert "MDF-e" in resposta.json()["detail"]

    async def test_mdfe_erro_de_valor_do_gerador_nao_vira_500(self, cliente, monkeypatch) -> None:
        """Contrato do ``except ValueError``: erro de valor é dado inválido (422).

        O schema de entrada já exige chave de 44 dígitos, descarga e município de
        carregamento, então esse ramo não é alcançável por HTTP hoje. O teste injeta
        a falha para provar que, se o gerador passar a levantar ``ValueError``, a
        rota continua respondendo 422 em vez de 500.
        """
        tenant = await tenant_que_pode_emitir(cliente, "mdfe-valueerror")

        from app.api.v1 import transportes

        def gerador_que_recusa(dados, certificado):
            raise ValueError("MDF-e exige ao menos uma chave de NF-e em infDoc")

        monkeypatch.setattr(transportes, "gerar_mdfe", gerador_que_recusa)

        resposta = await cliente.post(
            "/v1/transportes/mdfe", json=mdfe_base(), headers=cabecalho(tenant)
        )

        assert resposta.status_code == 422, resposta.text
        assert "chave de NF-e" in resposta.json()["detail"]


# ---------------------------------------------------------------------------
# integracoes.py — pré-requisito do tenant e recusa da SEFIN
# ---------------------------------------------------------------------------
async def _evento_dz23(cliente, tenant: dict[str, Any], evento_id: str):
    return await cliente.post(
        "/v1/integracoes/dz23/vendas",
        json={
            "evento_id": evento_id,
            "valor": 10.00,
            "descricao": "Serviço",
            "cliente": {"nome": "Cliente Teste"},
        },
        headers=cabecalho(tenant),
    )


class TestIntegracoesRecusas:
    async def test_certificado_ambiguo_e_422_e_nao_grava_fatura(self, cliente, sessao_db) -> None:
        """Dois A1 ativos = ambiguidade declarada (§80) → 422 sem efeito colateral."""
        tenant = await tenant_que_pode_emitir(cliente, "int-cert-ambiguo")
        # Segundo upload desativa o primeiro; forçamos os dois ativos no banco para
        # reproduzir o estado que ``certificados.ativo`` recusa.
        await enviar_certificado(cliente, tenant)

        from app.db.models.tenant import Tenant, TenantCertificate

        registro_tenant = (
            await sessao_db.execute(select(Tenant).where(Tenant.slug == "int-cert-ambiguo"))
        ).scalar_one()
        registros = (
            (
                await sessao_db.execute(
                    select(TenantCertificate).where(
                        TenantCertificate.tenant_id == registro_tenant.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(registros) == 2, "o segundo upload deveria ter criado outro registro"
        for registro in registros:
            registro.ativo = True
        await sessao_db.commit()

        resposta = await _evento_dz23(cliente, tenant, "amb-1")

        assert resposta.status_code == 422, resposta.text
        corpo = resposta.json()
        assert corpo["motivo"] == "certificado_invalido"
        assert "mais de um certificado ativo" in corpo["mensagem"]

        # O rollback da rota precisa desfazer a fatura criada antes da emissão.
        from app.db.models.invoice import Invoice

        fatura = (
            await sessao_db.execute(select(Invoice).where(Invoice.idempotency_key == "dz23:amb-1"))
        ).scalar_one_or_none()
        assert fatura is None, "evento recusado não pode deixar fatura pendente"

    async def test_recusa_da_sefin_vira_422_com_o_tipo(self, cliente, monkeypatch) -> None:
        """``ErroSefin`` chega ao parceiro como 422 com ``motivo`` legível, não 500."""
        tenant = await tenant_que_pode_emitir(cliente, "int-sefin-recusa")

        from app.api.v1 import integracoes
        from app.nfse.errors import ErroSefin, TipoErroFiscal

        async def sefin_recusa(*args, **kwargs):
            raise ErroSefin(tipo=TipoErroFiscal.REJEICAO, resumo="DPS recusada pela SEFIN")

        monkeypatch.setattr(integracoes.emissao_service, "emitir", sefin_recusa)

        resposta = await _evento_dz23(cliente, tenant, "sefin-1")

        assert resposta.status_code == 422, resposta.text
        corpo = resposta.json()
        assert corpo["motivo"] == TipoErroFiscal.REJEICAO.value
        assert "DPS recusada pela SEFIN" in corpo["mensagem"]


# ---------------------------------------------------------------------------
# representacoes.py — limites, DANFSe e falha do registro
# ---------------------------------------------------------------------------
class TestRepresentacoesBordas:
    async def test_xml_acima_do_limite_e_413(self, cliente) -> None:
        tenant = await criar_tenant(cliente, "repr-grande")
        grande = b" " * (5 * 1024 * 1024 + 1)

        resposta = await cliente.post(
            "/v1/representacoes?formato=danfe",
            files={"arquivo": ("grande.xml", grande, "application/xml")},
            headers=cabecalho(tenant),
        )

        assert resposta.status_code == 413, resposta.text
        assert "5 MB" in resposta.json()["detail"]

    async def test_danfse_de_xml_nfse(self, cliente) -> None:
        """``formato=danfse`` instancia a representação de NFS-e, não a de NF-e."""
        tenant = await criar_tenant(cliente, "repr-danfse")

        resposta = await cliente.post(
            "/v1/representacoes?formato=danfse",
            files={"arquivo": ("nfse.xml", NFSE_XML.encode("utf-8"), "application/xml")},
            headers=cabecalho(tenant),
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.headers["content-type"] == "application/pdf"
        assert resposta.content.startswith(b"%PDF")
        assert 'filename="danfse.pdf"' in resposta.headers["content-disposition"]
        texto = "\n".join(
            p.extract_text() or "" for p in PdfReader(BytesIO(resposta.content)).pages
        )
        assert "BARBEARIA CENTRO LTDA" in texto

    async def test_falha_ao_obter_a_representacao_vira_422(self, cliente, monkeypatch) -> None:
        """Registro sem a representação pedida é 422 com o motivo, não 500.

        Injeção explícita: o catálogo atual sempre resolve o que lista, então o ramo
        só é alcançável por falha do próprio registro. O contrato a provar é a
        tradução de ``ErroRepresentacao`` em 422.
        """
        tenant = await criar_tenant(cliente, "repr-registro")

        from app.api.v1 import representacoes
        from app.danfe import RepresentacaoNaoImplementada

        def sem_representacao(documento: str, formato: str):
            raise RepresentacaoNaoImplementada(f"layout {formato!r} não implementado")

        monkeypatch.setattr(representacoes, "obter", sem_representacao)

        resposta = await cliente.post(
            "/v1/representacoes?formato=danfe",
            files={"arquivo": ("nfe.xml", nfe(), "application/xml")},
            headers=cabecalho(tenant),
        )

        assert resposta.status_code == 422, resposta.text
        assert "não implementado" in resposta.json()["detail"]

    async def test_falha_na_geracao_vira_422(self, cliente, monkeypatch) -> None:
        """``ErroRepresentacao`` levantado pelo gerador também é 422 (defesa em profundidade)."""
        tenant = await criar_tenant(cliente, "repr-gerador")

        from app.api.v1 import representacoes
        from app.danfe import RepresentacaoNaoImplementada

        class GeradorQuebrado:
            def gerar(self, conteudo: bytes) -> bytes:
                raise RepresentacaoNaoImplementada("gerador indisponível")

        monkeypatch.setattr(representacoes, "obter", lambda documento, formato: GeradorQuebrado())

        resposta = await cliente.post(
            "/v1/representacoes?formato=danfe",
            files={"arquivo": ("nfe.xml", nfe(), "application/xml")},
            headers=cabecalho(tenant),
        )

        assert resposta.status_code == 422, resposta.text
        assert "gerador indisponível" in resposta.json()["detail"]


# ---------------------------------------------------------------------------
# admin.py — revogação de chave para tenant inexistente
# ---------------------------------------------------------------------------
CHAVE_ADMIN = "chave-de-admin-para-teste-123456"


@pytest.fixture
def admin_ligado(app_teste):
    from app.core.config import Settings, get_settings

    conf = Settings(environment="test", admin_habilitado=True, admin_api_key=CHAVE_ADMIN)
    app_teste.dependency_overrides[get_settings] = lambda: conf
    yield {"X-Admin-Key": CHAVE_ADMIN}
    app_teste.dependency_overrides.clear()


class TestAdminRevogarChave:
    async def test_tenant_inexistente_da_404(self, cliente, admin_ligado) -> None:
        alvo = uuid.uuid4()

        resposta = await cliente.post(
            f"/v1/admin/tenants/{alvo}/revogar-chave", headers=admin_ligado
        )

        assert resposta.status_code == 404, resposta.text
        assert resposta.json()["detail"] == "tenant não encontrado"

    async def test_404_em_outro_id_nao_revoga_tenant_existente(self, cliente, admin_ligado) -> None:
        """Isolamento: o 404 não pode ser um efeito colateral sobre o tenant errado."""
        tenant = await criar_tenant(cliente, "admin-intacto")

        await cliente.post(f"/v1/admin/tenants/{uuid.uuid4()}/revogar-chave", headers=admin_ligado)

        assert (await cliente.get("/v1/me", headers=cabecalho(tenant))).status_code == 200


# ---------------------------------------------------------------------------
# tenants.py — violação de unicidade vinda do banco
# ---------------------------------------------------------------------------
class TestTenantViolacaoDeUnicidade:
    async def test_integrity_error_vira_409_e_desfaz_a_insercao(
        self, cliente, sessao_db, monkeypatch
    ) -> None:
        """Corrida perdida na unicidade do slug é 409 com rollback, não 500.

        ``criar_tenant`` já checa o slug e levanta ``SlugJaExiste``; o
        ``IntegrityError`` é a rede para a corrida entre a checagem e o INSERT. O
        teste injeta a violação **depois** de inserir e dar flush, que é o cenário
        real, e verifica que o rollback desfaz a linha.
        """
        from app.api.v1 import tenants as rota_tenants
        from app.db.models.tenant import Tenant

        async def insere_e_colide(sessao, dados):
            sessao.add(
                Tenant(
                    slug=dados.slug,
                    nome=dados.nome,
                    api_key_prefix="corrida-",
                    api_key_hash="0" * 64,
                )
            )
            await sessao.flush()
            raise IntegrityError("INSERT INTO tenants", {}, Exception("duplicate key"))

        monkeypatch.setattr(rota_tenants.service, "criar_tenant", insere_e_colide)

        resposta = await cliente.post(
            "/v1/tenants", json={"slug": "corrida", "nome": "Corrida LTDA"}
        )

        assert resposta.status_code == 409, resposta.text
        assert resposta.json()["detail"] == "violação de unicidade ao criar tenant"

        listagem = (await cliente.get("/v1/tenants")).json()
        assert listagem["total"] == 0, "rollback deveria ter desfeito o INSERT"
        assert (
            await sessao_db.execute(select(Tenant).where(Tenant.slug == "corrida"))
        ).scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# deps.py — credencial revogada e admin desabilitado em produção
# ---------------------------------------------------------------------------
class TestDependenciasDeAutenticacao:
    async def test_credencial_revogada_da_401_com_motivo(self, cliente, sessao_db) -> None:
        """Chave revogada diz que foi revogada: retry eterno com credencial morta é pior.

        O fluxo de revogação por rota também troca o hash, então a chave deixa de casar
        e a resposta é "credencial inválida". O estado testado aqui — hash ainda
        casando, carimbo de revogação presente — é o que a dependência precisa
        distinguir para o dono não insistir.
        """
        tenant = await criar_tenant(cliente, "dep-revogada")

        from app.db.models.tenant import Tenant

        registro = (
            await sessao_db.execute(select(Tenant).where(Tenant.slug == "dep-revogada"))
        ).scalar_one()
        registro.api_key_revogada_em = datetime.now(UTC)
        await sessao_db.commit()

        resposta = await cliente.get("/v1/me", headers=cabecalho(tenant))

        assert resposta.status_code == 401, resposta.text
        assert "revogada" in resposta.json()["detail"]
        assert resposta.headers.get("WWW-Authenticate") == "ApiKey"

    async def test_admin_sem_token_em_producao_da_503(self, cliente, app_teste) -> None:
        """Em produção, rota administrativa sem ``ADMIN_API_TOKEN`` é 503, não aberta."""
        from app.core.config import Settings, get_settings

        app_teste.dependency_overrides[get_settings] = lambda: Settings(
            environment="production", admin_api_token=""
        )
        try:
            resposta = await cliente.get("/v1/tenants")
        finally:
            app_teste.dependency_overrides.clear()

        assert resposta.status_code == 503, resposta.text
        assert "ADMIN_API_TOKEN" in resposta.json()["detail"]


# ---------------------------------------------------------------------------
# apuracoes.py — guia de apuração inexistente ou de outro tenant
# ---------------------------------------------------------------------------
class TestApuracaoGuiaRecusas:
    async def test_guia_de_apuracao_inexistente_da_404(self, cliente) -> None:
        tenant = await criar_tenant(cliente, "ap-guia-inexistente")
        apuracao_id = uuid.uuid4()

        resposta = await cliente.post(
            f"/v1/apuracoes/{apuracao_id}/guia", headers=cabecalho(tenant)
        )

        assert resposta.status_code == 404, resposta.text
        assert "não encontrada" in resposta.json()["detail"]

    async def test_guia_de_outro_tenant_da_404_e_nao_gera(self, cliente) -> None:
        dono = await criar_tenant(cliente, "ap-dono")
        criada = await cliente.post(
            "/v1/apuracoes", json={"competencia": "2026-05"}, headers=cabecalho(dono)
        )
        assert criada.status_code == 200, criada.text
        apuracao_id = criada.json()["id"]

        vizinho = await criar_tenant(cliente, "ap-vizinho")
        resposta = await cliente.post(
            f"/v1/apuracoes/{apuracao_id}/guia", headers=cabecalho(vizinho)
        )

        assert resposta.status_code == 404, resposta.text
        # O dono continua sem guia: a tentativa alheia não pode ter gerado nada.
        detalhe = await cliente.get(f"/v1/apuracoes/{apuracao_id}", headers=cabecalho(dono))
        assert detalhe.status_code == 200
        assert detalhe.json()["guia_numero"] is None


# ---------------------------------------------------------------------------
# health.py — Redis fora do ar no batimento do worker
# ---------------------------------------------------------------------------
class TestSaudeSemBatimento:
    @staticmethod
    def _quebrar_leitura_do_batimento(monkeypatch) -> None:
        """Mantém o PING real e falha só no ``GET`` que lê o batimento do worker.

        Não dá para trocar ``obter_redis`` por uma função que sempre levanta: o
        ``ping_redis`` usa a mesma função, e o teste passaria a medir a mentira em vez
        do comportamento. Aqui a dependência continua real e só a leitura do
        batimento falha.
        """
        from app.core import redis as redis_module

        original = redis_module.obter_redis

        class RedisSemLeituraDeBatimento:
            def __init__(self, cliente) -> None:
                self._cliente = cliente

            def __getattr__(self, nome: str):
                if nome == "get":

                    async def falha(*args, **kwargs):
                        raise RuntimeError("falha ao ler o batimento")

                    return falha
                return getattr(self._cliente, nome)

        monkeypatch.setattr(
            redis_module,
            "obter_redis",
            lambda: RedisSemLeituraDeBatimento(original()),
        )

    async def test_redis_fora_nao_derruba_a_readiness(self, cliente, monkeypatch) -> None:
        """Falha ao ler o batimento é reportada, não transformada em 500/503.

        O ``/health`` continua 200 porque banco e Redis (PING) respondem; o worker é
        reportado como não-ok com o tipo da falha — o operador sabe onde olhar.
        """
        self._quebrar_leitura_do_batimento(monkeypatch)

        resposta = await cliente.get("/health")

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["worker"]["ok"] is False
        assert "RuntimeError" in corpo["worker"]["detalhe"]
        assert corpo["verificacoes"]["database"]["ok"] is True
        assert corpo["verificacoes"]["redis"]["ok"] is True

    async def test_flag_do_worker_reprova_mesmo_com_banco_e_redis_ok(
        self, cliente, app_teste, monkeypatch
    ) -> None:
        from app.core.config import Settings, get_settings

        self._quebrar_leitura_do_batimento(monkeypatch)
        app_teste.dependency_overrides[get_settings] = lambda: Settings(
            environment="test", readiness_exige_worker=True
        )
        try:
            resposta = await cliente.get("/health")
        finally:
            app_teste.dependency_overrides.clear()

        assert resposta.status_code == 503, resposta.text
        corpo = resposta.json()
        assert corpo["status"] == "degraded"
        assert corpo["verificacoes"]["database"]["ok"] is True
        assert corpo["verificacoes"]["redis"]["ok"] is True
        assert corpo["worker"]["ok"] is False


# ---------------------------------------------------------------------------
# municipios.py — filtros de nome e de homologação
# ---------------------------------------------------------------------------
class TestMunicipiosFiltros:
    @pytest.fixture
    async def acervo(self, sessao_db):
        from app.db.models.municipio import MunicipioNFSe, ProvedorNFSe

        for codigo, nome, uf, provedor, homologado in [
            ("5208707", "Goiania", "GO", ProvedorNFSe.NACIONAL_REST, True),
            ("3550308", "Sao Paulo", "SP", ProvedorNFSe.ABRASF_2_04, False),
            ("3304557", "Rio de Janeiro", "RJ", ProvedorNFSe.ABRASF_2_04, False),
        ]:
            sessao_db.add(
                MunicipioNFSe(
                    codigo_ibge=codigo,
                    nome=nome,
                    uf=uf,
                    provedor=provedor,
                    homologado=homologado,
                    fonte_url="https://servicodados.ibge.gov.br/api/v1/localidades/municipios",
                )
            )
        await sessao_db.commit()

    async def test_filtra_por_prefixo_do_nome(self, cliente, acervo) -> None:
        corpo = (await cliente.get("/v1/municipios?nome=Goi")).json()

        assert corpo["total"] == 1, corpo
        assert [m["codigo_ibge"] for m in corpo["itens"]] == ["5208707"]

    async def test_filtra_por_homologado(self, cliente, acervo) -> None:
        homologados = (await cliente.get("/v1/municipios?homologado=true")).json()
        nao_homologados = (await cliente.get("/v1/municipios?homologado=false")).json()

        assert homologados["total"] == 1, homologados
        assert [m["codigo_ibge"] for m in homologados["itens"]] == ["5208707"]
        assert nao_homologados["total"] == 2, nao_homologados
        assert {m["codigo_ibge"] for m in nao_homologados["itens"]} == {
            "3550308",
            "3304557",
        }
