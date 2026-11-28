"""Ramos de serviço que a suíte não alcançava.

Cada teste aqui existe porque uma linha de `app/` ficava sem execução medida. O
critério não é "passou": é a linha do código de produção passar a guardar um
comportamento observável — valor devolvido, exceção de domínio específica, efeito
no estado do banco, ou isolamento entre tenants.

Dois grupos:

- **sem banco**: funções puras (datas, decimal, schema, cofre, assinatura);
- **com banco** (`sessao_db`, Postgres do compose): repositórios e serviços.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import logging
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.assessment.providers import DadosApuracao, ProvedorManDna
from app.batches import csv as csv_lote
from app.catalogo import (
    Cobertura,
    ErroDeImportacao,
    LinhaEndpoints,
    Plano,
    aplicar_endpoints_sefaz,
    medir_cobertura,
    planejar_endpoints_sefaz,
    validar_linha,
    validar_lote,
)
from app.cep import client as cep_client
from app.cep.service import ServicoCep
from app.certificates import service as certificados
from app.core import errors as erros
from app.core import ratelimit, vault
from app.core import schemas as schemas_xsd
from app.core.circuit import CircuitBreaker
from app.core.config import Settings, get_settings, reload_settings
from app.db.models.enums import StatusTenant
from app.db.models.invoice import Invoice
from app.db.models.tenant import Tenant
from app.db.models.webservice_sefaz import VersaoSOAP, WebserviceSefaz
from app.frete import oauth
from app.integrations.base import ErroDeIntegracao, exigir, para_decimal
from app.tax import auditoria_service as auditoria
from app.tax import classificacoes
from app.tax.auditoria import LaudoCalculo, TabelaConsultada
from app.tax.schemas import SimulacaoIn
from app.tenants import repository as tenant_repo
from app.tenants import service as tenants
from app.tenants.schemas import TenantCreate
from app.webhooks import assinatura
from app.worker import dlq
from pydantic import ValidationError
from sqlalchemy import select

from tests.test_fase2_certificado import SENHA, gerar_pfx


def _criar_tenant(sessao, slug: str) -> Tenant:
    """Tenant mínimo persistível (o modelo exige prefixo e hash de credencial)."""
    registro = Tenant(
        slug=slug,
        nome=f"Tenant {slug}",
        api_key_prefix=slug[:8],
        api_key_hash=f"hash-{slug}".ljust(64, "0")[:64],
    )
    sessao.add(registro)
    return registro


def _resposta(status: int, *, json_body: Any = None, texto: str | None = None) -> httpx.Response:
    pedido = httpx.Request("POST", "https://melhorenvio.test/oauth/token")
    if texto is not None:
        return httpx.Response(status, text=texto, request=pedido)
    return httpx.Response(status, json=json_body, request=pedido)


# ---------------------------------------------------------------------------
# tenants/service.py
# ---------------------------------------------------------------------------
class TestTenantServicoRamos:
    async def test_slug_duplicado_na_corrida_vira_erro_de_dominio(
        self, sessao_db, monkeypatch
    ) -> None:
        """A checagem por slug e o INSERT não são atômicos: entre eles cabe outro pedido.

        Aqui a janela é aberta de propósito (a checagem "não vê" o registro que já
        existe). O `IntegrityError` do banco precisa virar `SlugJaExiste` — erro de
        domínio, com rollback — e não um 500 com a sessão envenenada.
        """
        await tenants.criar_tenant(sessao_db, TenantCreate(slug="corrida", nome="Corrida LTDA"))
        await sessao_db.commit()

        async def sem_checagem(sessao, slug):
            return None

        monkeypatch.setattr(tenant_repo, "por_slug", sem_checagem)

        with pytest.raises(tenants.SlugJaExiste, match="corrida"):
            await tenants.criar_tenant(sessao_db, TenantCreate(slug="corrida", nome="Outra LTDA"))

        # O rollback deixou a sessão utilizável e não houve segundo tenant.
        registros = (
            (await sessao_db.execute(select(Tenant).where(Tenant.slug == "corrida")))
            .scalars()
            .all()
        )
        assert len(registros) == 1

    async def test_chave_revogada_tem_precedencia_sobre_a_expirada(self, sessao_db) -> None:
        """Com os dois carimbos, o motivo comunicado é revogação — a chave não volta por rotação.

        A ordem importa: quem teve a chave vazada precisa saber que ela foi morta, e não
        que "expirou" (o que sugeriria esperar ou renovar).
        """
        tenant, chave, _ = await tenants.criar_tenant(
            sessao_db, TenantCreate(slug="rev-exp", nome="Revogada LTDA")
        )
        await sessao_db.commit()

        registro = (
            await sessao_db.execute(select(Tenant).where(Tenant.id == tenant.id))
        ).scalar_one()
        registro.api_key_revogada_em = datetime.now(UTC) - timedelta(days=2)
        registro.api_key_expira_em = datetime.now(UTC) - timedelta(days=1)
        await sessao_db.commit()

        with pytest.raises(tenants.CredencialRevogada, match="revogada"):
            await tenants.autenticar(sessao_db, chave)

    async def test_expiracao_sem_fuso_no_banco_nao_derruba_a_autenticacao(
        self, monkeypatch
    ) -> None:
        """Validade gravada sem fuso é lida como UTC, não como "já venceu".

        O `replace(tzinfo=UTC)` existe porque comparar aware com naive levanta
        `TypeError` — que viraria 500 na autenticação, não 401.
        """
        chave = "nb_" + "a" * 40
        valido = Tenant(
            slug="sem-fuso",
            nome="Sem Fuso LTDA",
            api_key_prefix="nb_00000000",
            api_key_hash="0" * 64,
            status=StatusTenant.ATIVO,
        )
        valido.api_key_expira_em = datetime.now() + timedelta(days=1)  # naive
        valido.api_key_revogada_em = None

        async def por_hash(sessao, hash_recebido):
            return valido

        monkeypatch.setattr(tenant_repo, "por_hash_de_chave", por_hash)

        assert (await tenants.autenticar(None, chave)).slug == "sem-fuso"

        valido.api_key_expira_em = datetime.now() - timedelta(days=1)  # naive, já venceu
        with pytest.raises(tenants.CredencialExpirada, match="expirada"):
            await tenants.autenticar(None, chave)

    async def test_obter_tenant_devolve_o_registro_existente(self, sessao_db) -> None:
        tenant, _, _ = await tenants.criar_tenant(
            sessao_db, TenantCreate(slug="obtem", nome="Obtém LTDA")
        )
        await sessao_db.commit()

        encontrado = await tenants.obter_tenant(sessao_db, tenant.id)
        assert encontrado.id == tenant.id
        assert encontrado.slug == "obtem"


# ---------------------------------------------------------------------------
# integrations/base.py
# ---------------------------------------------------------------------------
class TestIntegracaoBase:
    def test_tipo_errado_diz_qual_tipo_era_esperado(self) -> None:
        # A mensagem precisa servir para o parceiro corrigir o payload sem abrir o código.
        with pytest.raises(ErroDeIntegracao, match="deveria ser str"):
            exigir({"valor": 10}, "valor", tipo=str)

    def test_decimal_recebido_volta_intacto(self) -> None:
        valor = Decimal("12.34")
        assert para_decimal(valor, "valor") is valor

    def test_virgula_decimal_sem_milhar(self) -> None:
        assert para_decimal("100,50", "valor") == Decimal("100.50")

    def test_texto_nao_numerico_e_recusado(self) -> None:
        with pytest.raises(ErroDeIntegracao, match="valor monetário"):
            para_decimal("abc", "valor")

    def test_tipo_que_nao_e_numero_nem_texto_e_recusado(self) -> None:
        with pytest.raises(ErroDeIntegracao, match="valor monetário"):
            para_decimal(["1"], "valor")


# ---------------------------------------------------------------------------
# frete/oauth.py
# ---------------------------------------------------------------------------
class TestOauthFalhas:
    def test_falha_de_rede_vira_erro_do_melhor_envio(self, monkeypatch) -> None:
        def explode(self, url, json=None, headers=None):
            raise httpx.ConnectError("sem rede")

        monkeypatch.setattr(httpx.Client, "post", explode)
        with pytest.raises(oauth.ErroMelhorEnvio, match="falha de rede"):
            oauth.trocar_codigo(
                code="c", client_id="i", client_secret="s", redirect_uri="https://x/cb"
            )

    def test_http_500_da_api_vira_erro_com_o_status(self, monkeypatch) -> None:
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, json=None, headers=None: _resposta(500, texto="boom"),
        )
        with pytest.raises(oauth.ErroMelhorEnvio, match="HTTP 500"):
            oauth.renovar(refresh_token="r", client_id="i", client_secret="s")

    def test_resposta_que_nao_e_json(self, monkeypatch) -> None:
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, json=None, headers=None: _resposta(
                200, texto="<html>manutenção</html>"
            ),
        )
        with pytest.raises(oauth.ErroMelhorEnvio, match="não é JSON"):
            oauth.renovar(refresh_token="r", client_id="i", client_secret="s")

    def test_expires_in_ilegivel_nao_quebra_a_renovacao(self, monkeypatch) -> None:
        """`expires_in` não numérico vira "sem prazo conhecido", não exceção.

        O token é válido; recusar a renovação por causa do campo de prazo trocaria
        credencial boa por falha operacional.
        """
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, json=None, headers=None: _resposta(
                200, json_body={"access_token": "novo", "expires_in": "muitos segundos"}
            ),
        )
        token = oauth.renovar(refresh_token="r", client_id="i", client_secret="s")

        assert token.access_token == "novo"
        assert token.expira_em is None
        assert token.expirado is False


# ---------------------------------------------------------------------------
# catalogo/__init__.py
# ---------------------------------------------------------------------------
LINHA_ENDPOINT: dict[str, Any] = {
    "uf": "MT",
    "ambiente": "2",
    "servico": "NFeAutorizacao",
    "url": "https://homolog.sefaz.mt.gov.br/nfe",
    "versao_soap": "1.2",
    "fonte_url": "https://www.sefaz.mt.gov.br/nfe/manual.pdf",
}


class TestCatalogoRamos:
    def test_modelo_fora_do_catalogo_e_recusado(self) -> None:
        # 99 é modelo inexistente: aceitar criaria endpoint órfão.
        with pytest.raises(ErroDeImportacao, match="modelo inválido"):
            validar_linha({**LINHA_ENDPOINT, "modelo": "99"}, linha=2)

    def test_plano_vazio_tem_total_zero(self) -> None:
        assert Plano().total == 0
        assert (
            Plano(inserir=[LinhaEndpoints("MT", "2", "s", "https://x", "1.2", "https://y")]).total
            == 1
        )

    def test_cobertura_sem_ufs_nao_divide_por_zero(self) -> None:
        assert Cobertura(ufs_com_autorizacao=(), ufs_sem_autorizacao=()).percentual == 0.0

    async def test_url_alterada_e_gravada_no_banco(self, sessao_db) -> None:
        """`atualizar` não é só relatório: o plano aplicado muda url, versão e autorizador."""
        validas, erros = validar_lote([LINHA_ENDPOINT])
        assert not erros

        await aplicar_endpoints_sefaz(
            sessao_db, await planejar_endpoints_sefaz(sessao_db, validas), dry_run=False
        )
        await sessao_db.commit()

        novas, _ = validar_lote(
            [
                {
                    **LINHA_ENDPOINT,
                    "url": "https://novo.example/nfe",
                    "versao_soap": "1.1",
                    "versao_layout": "4.00",
                    "autorizador": "MT",
                }
            ]
        )
        plano = await planejar_endpoints_sefaz(sessao_db, novas)
        assert plano.total == 1
        assert len(plano.atualizar) == 1

        await aplicar_endpoints_sefaz(sessao_db, plano, dry_run=False)
        await sessao_db.commit()

        registro = (
            await sessao_db.execute(
                select(WebserviceSefaz).where(
                    WebserviceSefaz.uf == "MT", WebserviceSefaz.modelo == "55"
                )
            )
        ).scalar_one()
        assert registro.url == "https://novo.example/nfe"
        assert registro.versao_soap == VersaoSOAP("1.1")
        assert registro.versao_layout == "4.00"
        assert registro.autorizador == "MT"

    async def test_cobertura_so_conta_o_modelo_consultado(self, sessao_db) -> None:
        """55 e 65 têm conjuntos diferentes de UF: somar os dois mentiria a cobertura."""
        validas, _ = validar_lote([{**LINHA_ENDPOINT, "modelo": "65"}])
        await aplicar_endpoints_sefaz(
            sessao_db, await planejar_endpoints_sefaz(sessao_db, validas), dry_run=False
        )
        await sessao_db.commit()

        cobertura = await medir_cobertura(sessao_db, modelo="55")
        assert "MT" not in cobertura.ufs_com_autorizacao
        assert len(cobertura.ufs_sem_autorizacao) == 27


# ---------------------------------------------------------------------------
# cep/client.py
# ---------------------------------------------------------------------------
class TestCepClientRamos:
    async def test_brasilapi_sem_municipio_fecha_como_cep_inexistente(self) -> None:
        """Resposta 200 sem município não é "encontrado" nem "fonte fora do ar"."""

        def manipulador(request: httpx.Request) -> httpx.Response:
            if "viacep" in str(request.url):
                return httpx.Response(200, json={"erro": "true"}, request=request)
            return httpx.Response(200, json={}, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(manipulador)) as http:
            with pytest.raises(cep_client.CepNaoEncontrado, match="99999999"):
                await cep_client.consultar("99999999", cliente=http)

    async def test_cliente_proprio_e_fechado_ao_fim(self, monkeypatch) -> None:
        """Sem cliente injetado, o `AsyncClient` criado dentro é fechado — não vaza pool."""
        original = httpx.AsyncClient
        fechamentos: list[bool] = []

        class Espiao(original):
            async def aclose(self) -> None:
                fechamentos.append(True)
                await super().aclose()

        def fabrica(*args, **kwargs):
            return Espiao(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={
                            "logradouro": "Praça da Sé",
                            "localidade": "São Paulo",
                            "uf": "SP",
                            "ibge": "3550308",
                        },
                        request=request,
                    )
                )
            )

        monkeypatch.setattr(cep_client.httpx, "AsyncClient", fabrica)

        endereco = await cep_client.consultar("01001-000")

        assert endereco.fonte == "viacep"
        assert endereco.codigo_ibge == "3550308"
        assert fechamentos == [True]


# ---------------------------------------------------------------------------
# cep/service.py
# ---------------------------------------------------------------------------
class _CacheCorrompido:
    """Cache que devolve lixo: o serviço precisa degradar, não derrubar a consulta."""

    async def get(self, chave: str):
        return "{isto nao e json"

    async def set(self, chave, valor, ex=None) -> None:
        return None


class TestServicoCepRamos:
    async def test_cache_corrompido_cai_para_a_fonte(self, monkeypatch) -> None:
        chamadas = {"n": 0}

        async def falso(cep: str, *, cliente=None) -> cep_client.Endereco:
            chamadas["n"] += 1
            return cep_client._de_viacep(
                {"localidade": "Campinas", "uf": "SP", "ibge": "3509502"}, cep
            )

        monkeypatch.setattr("app.cep.service.consultar", falso)

        endereco = await ServicoCep(_CacheCorrompido()).buscar("13010-000")

        assert chamadas["n"] == 1, "cache ilegível não pode ser confundido com acerto"
        assert endereco.municipio == "Campinas"


# ---------------------------------------------------------------------------
# certificates/service.py
# ---------------------------------------------------------------------------
class TestCertificadoAvisos:
    async def test_certificado_vencido_e_aceito_com_aviso(self, sessao_db, caplog) -> None:
        """Recusar no upload esconderia o motivo: o usuário precisa ver "está vencido"."""
        tenant = _criar_tenant(sessao_db, "cert-vencido")
        await sessao_db.flush()

        with caplog.at_level(logging.WARNING, logger="app.certificates.service"):
            registro = await certificados.registrar(
                sessao_db,
                tenant.id,
                apelido="vencido",
                pfx=gerar_pfx(dias_validade=0),
                senha=SENHA.decode(),
            )
        await sessao_db.commit()

        assert registro.ativo is True
        assert "certificado_expirado_cadastrado" in caplog.text

    async def test_certificado_perto_de_expirar_gera_aviso(self, sessao_db, caplog) -> None:
        tenant = _criar_tenant(sessao_db, "cert-perto")
        await sessao_db.flush()

        with caplog.at_level(logging.WARNING, logger="app.certificates.service"):
            registro = await certificados.registrar(
                sessao_db,
                tenant.id,
                apelido="perto",
                pfx=gerar_pfx(dias_validade=20),
                senha=SENHA.decode(),
            )
        await sessao_db.commit()

        assert registro.ativo is True
        assert "certificado_perto_de_expirar" in caplog.text


# ---------------------------------------------------------------------------
# core/circuit.py
# ---------------------------------------------------------------------------
def test_circuito_fechado_nao_tem_espera_a_informar() -> None:
    """`retry_after_s` só faz sentido em ABERTO; devolver espera com o circuito fechado
    faria o cliente dormir à toa."""
    assert CircuitBreaker(nome="sefaz-51").retry_after_s() == 0.0


# ---------------------------------------------------------------------------
# core/config.py
# ---------------------------------------------------------------------------
def test_reload_settings_rele_o_ambiente_e_restaura(monkeypatch) -> None:
    original = get_settings()
    try:
        monkeypatch.setenv("LOG_LEVEL", "debug")
        nova = reload_settings()
        assert nova is not original, "reload precisa descartar o cache"
        assert nova.log_level == "DEBUG"
    finally:
        monkeypatch.undo()
        restaurada = reload_settings()
    assert restaurada.log_level == original.log_level


# ---------------------------------------------------------------------------
# core/errors.py
# ---------------------------------------------------------------------------
class TestProblemaRamos:
    def test_tenant_id_aparece_quando_informado(self) -> None:
        corpo = erros.Problema(
            titulo="t", status=422, detalhe="d", tenant_id="11111111-1111-1111-1111-111111111111"
        ).para_dict()
        assert corpo["tenant_id"] == "11111111-1111-1111-1111-111111111111"

    def test_detail_que_nao_e_texto_nem_dict_vira_string(self) -> None:
        corpo = erros.de_http_exception(400, 42).para_dict()
        assert corpo["detail"] == "42"
        assert corpo["status"] == 400

    def test_dict_sem_campo_de_resumo_vira_chave_valor(self) -> None:
        # Nunca `str(dict)`: o cliente receberia repr de Python, impossível de parsear.
        corpo = erros.de_http_exception(502, {"codigo": "539"}).para_dict()
        assert corpo["detail"] == "erro estruturado: codigo=539"
        assert corpo["codigo"] == "539", "os campos do dict continuam legíveis no corpo"


# ---------------------------------------------------------------------------
# core/ratelimit.py
# ---------------------------------------------------------------------------
class TestJanelaExpira:
    async def test_janela_expirada_zera_a_contagem(self, monkeypatch) -> None:
        relogio = {"agora": 1000.0}
        monkeypatch.setattr(ratelimit.time, "monotonic", lambda: relogio["agora"])

        store = ratelimit.ArmazenamentoMemoria()
        assert await store.incrementar("k", 60) == 1
        assert await store.incrementar("k", 60) == 2

        relogio["agora"] += 61
        assert await store.incrementar("k", 60) == 1, "janela nova recomeça em 1"
        assert await store.consultar("k") == 1


class _RedisLeitura:
    def __init__(self, valor: str | None) -> None:
        self._valor = valor
        self.chaves: list[str] = []

    async def get(self, chave: str):
        self.chaves.append(chave)
        return self._valor


class TestRedisRamos:
    async def test_consultar_le_a_chave_com_prefixo(self, monkeypatch) -> None:
        falso = _RedisLeitura("7")
        monkeypatch.setattr("app.core.redis.obter_redis", lambda: falso)

        assert await ratelimit.ArmazenamentoRedis(prefixo="p:").consultar("t1") == 7
        assert falso.chaves == ["p:t1"]

    async def test_consultar_sem_chave_devolve_zero(self, monkeypatch) -> None:
        monkeypatch.setattr("app.core.redis.obter_redis", lambda: _RedisLeitura(None))
        assert await ratelimit.ArmazenamentoRedis().consultar("t1") == 0


# ---------------------------------------------------------------------------
# core/schemas.py
# ---------------------------------------------------------------------------
class TestManifestoRamos:
    def test_manifesto_que_nao_e_objeto_e_recusado(self, tmp_path: Path) -> None:
        arquivo = tmp_path / "m.json"
        arquivo.write_text(json.dumps([1, 2]), encoding="utf-8")

        with pytest.raises(schemas_xsd.ErroDeIntegridade, match="objeto"):
            schemas_xsd.carregar_manifesto(arquivo)

    def test_gerar_manifesto_de_diretorio_inexistente(self, tmp_path: Path) -> None:
        with pytest.raises(schemas_xsd.ErroDeIntegridade, match="inexistente"):
            schemas_xsd.gerar_manifesto(tmp_path / "nada")


# ---------------------------------------------------------------------------
# core/vault.py
# ---------------------------------------------------------------------------
def test_abrir_e_selar_em_volta_do_cofre_configurado() -> None:
    import base64

    conf = Settings(
        environment="development",
        master_encryption_key=base64.b64encode(b"\x07" * 32).decode(),
    )
    envelope = vault.selar(b"segredo-do-tenant", aad=b"ctx", settings=conf)

    assert vault.abrir(envelope, aad=b"ctx", settings=conf) == b"segredo-do-tenant"


# ---------------------------------------------------------------------------
# tax/auditoria_service.py
# ---------------------------------------------------------------------------
def _laudo(**extra: Any) -> LaudoCalculo:
    base: dict[str, Any] = dict(
        entrada={"base": Decimal("100.00")},
        saida={"iss": Decimal("5.00")},
        regras=("ISS 5%",),
        tabelas=(TabelaConsultada("iss", "2026.1", date(2026, 1, 1)),),
        data_emissao=date(2026, 11, 25),
        trace_id="trace-doc",
    )
    base.update(extra)
    return LaudoCalculo(**base)


class TestAuditoriaPorDocumento:
    async def test_so_devolve_calculos_do_documento_e_do_tenant(self, sessao_db) -> None:
        tenant = _criar_tenant(sessao_db, "audit-doc")
        outro = _criar_tenant(sessao_db, "audit-doc-outro")
        await sessao_db.flush()

        fatura = Invoice(
            tenant_id=tenant.id,
            idempotency_key="audit-doc-1",
            valor_servico=Decimal("10.00"),
            descricao_servico="serviço",
        )
        sessao_db.add(fatura)
        await sessao_db.flush()

        await auditoria.registrar(
            sessao_db, tenant_id=tenant.id, laudo=_laudo(trace_id="t1"), invoice_id=fatura.id
        )
        await auditoria.registrar(
            sessao_db,
            tenant_id=tenant.id,
            laudo=_laudo(trace_id="t2", saida={"iss": Decimal("2.00")}),
            invoice_id=fatura.id,
        )
        await auditoria.registrar(sessao_db, tenant_id=tenant.id, laudo=_laudo(trace_id="t3"))
        await sessao_db.commit()

        do_documento = await auditoria.do_documento(
            sessao_db, tenant_id=tenant.id, invoice_id=fatura.id
        )
        assert {registro.trace_id for registro in do_documento} == {"t1", "t2"}

        # O mesmo id de documento, visto por outro tenant, não devolve nada.
        assert (
            await auditoria.do_documento(sessao_db, tenant_id=outro.id, invoice_id=fatura.id) == []
        )


# ---------------------------------------------------------------------------
# tax/classificacoes.py
# ---------------------------------------------------------------------------
@pytest.fixture
def catalogo_sintetico(tmp_path: Path, monkeypatch) -> Path:
    """Catálogo com uma versão *encerrada* — o arquivo real não tem `fim_vigencia`.

    O caso importa: uma versão com data-fim precisa sair de `vigentes_em` e fazer
    `buscar(..., quando=<depois do fim>)` devolver `None`, em vez de reaproveitar a
    classificação antiga.
    """
    arquivo = tmp_path / "classificacoes.json"
    arquivo.write_text(
        json.dumps(
            {
                "fonte": "teste",
                "classificacoes": [
                    {
                        "id": "1",
                        "codigo": "000001",
                        "descricao": "versao encerrada",
                        "inicio_vigencia": "2026-01-01",
                        "fim_vigencia": "2026-12-31",
                    },
                    {
                        "id": "2",
                        "codigo": "000002",
                        "descricao": "versao nova",
                        "inicio_vigencia": "2027-01-01",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(classificacoes, "CAMINHO_DADOS", arquivo)
    classificacoes._carregar.cache_clear()
    yield arquivo
    classificacoes._carregar.cache_clear()


class TestClassificacaoVigencia:
    def test_vigente_em_respeita_os_dois_limites(self) -> None:
        classificacao = classificacoes.Classificacao(
            id="x",
            codigo="000001",
            descricao="faixa fechada",
            inicio_vigencia="2026-01-01",
            fim_vigencia="2026-12-31",
        )
        assert classificacao.vigente_em(date(2026, 6, 1)) is True
        assert classificacao.vigente_em(date(2025, 12, 31)) is False
        assert classificacao.vigente_em(date(2027, 1, 1)) is False

    def test_vigentes_em_exclui_versao_encerrada(self, catalogo_sintetico: Path) -> None:
        vigentes = {c.codigo: c for c in classificacoes.vigentes_em(date(2027, 6, 1))}

        assert "000001" not in vigentes
        assert vigentes["000002"].descricao == "versao nova"

        de_2026 = {c.codigo: c for c in classificacoes.vigentes_em(date(2026, 6, 1))}
        assert de_2026["000001"].descricao == "versao encerrada"
        assert "000002" not in de_2026, "vigência futura não vale para 2026"

    def test_buscar_depois_do_fim_da_vigencia_devolve_none(self, catalogo_sintetico: Path) -> None:
        assert classificacoes.buscar("000001", quando=date(2027, 6, 1)) is None
        assert classificacoes.buscar("000001", quando=date(2026, 6, 1)) is not None
        assert classificacoes.buscar("000001") is not None


# ---------------------------------------------------------------------------
# tax/schemas.py
# ---------------------------------------------------------------------------
class TestSimulacaoSchema:
    def test_aliquota_de_ibs_sozinha_e_recusada(self) -> None:
        """Uma alíquota só produziria total que não existe em nenhuma tabela."""
        with pytest.raises(ValidationError, match="duas alíquotas"):
            SimulacaoIn(valor_servico=Decimal("100.00"), aliquota_ibs=Decimal("0.001"))

    def test_par_de_aliquotas_e_aceito(self) -> None:
        entrada = SimulacaoIn(
            valor_servico=Decimal("100.00"),
            aliquota_cbs=Decimal("0.009"),
            aliquota_ibs=Decimal("0.001"),
        )
        assert entrada.aliquota_cbs == Decimal("0.009")
        assert entrada.aliquota_ibs == Decimal("0.001")


# ---------------------------------------------------------------------------
# assessment/providers.py
# ---------------------------------------------------------------------------
def test_vencimento_de_competencia_de_dezembro_cai_no_ano_seguinte() -> None:
    dados = DadosApuracao(
        tenant_id="11111111-1111-1111-1111-111111111111",
        competencia="2026-12",
        total_servicos=Decimal("100.00"),
        total_iss=Decimal("5.00"),
        total_tributos=Decimal("5.00"),
        quantidade_documentos=1,
    )
    guia = ProvedorManDna().gerar(dados)

    assert guia.vencimento == date(2027, 1, 20), "dia 20 do mês seguinte à competência"


# ---------------------------------------------------------------------------
# batches/csv.py
# ---------------------------------------------------------------------------
CABECALHO_LOTE = "idempotency_key,valor,descricao,competencia,tomador_nome,tomador_documento"


def _csv(*linhas: str) -> bytes:
    return ("\n".join([CABECALHO_LOTE, *linhas]) + "\n").encode()


class TestCsvRamos:
    def test_arquivo_indecodificavel_e_recusado(self) -> None:
        # Bytes indefinidos em cp1252 (0x81/0x8D): nenhuma das três codificações serve.
        with pytest.raises(csv_lote.CsvInvalido, match="decodificar"):
            csv_lote.ler_csv(b"idempotency_key,valor,descricao\n\x81\x8d,10.00,x\n")

    def test_valor_em_branco_e_ausente_e_nao_zero(self) -> None:
        lote = csv_lote.ler_csv(_csv("chave-branco,,Serviço,,,"))

        assert lote.invalidas[0].valor is None
        assert lote.invalidas[0].erro == "valor ausente ou inválido"

    def test_virgula_decimal_sem_milhar(self) -> None:
        lote = csv_lote.ler_csv(_csv('chave-virgula,"100,50",Serviço,,,'))

        assert lote.validas[0].valor == Decimal("100.50")

    def test_regra_de_chave_vazia_recusa_a_linha(self) -> None:
        """A regra existe em `_validar`, mesmo com `ler_csv` não a chamando hoje.

        Este teste fixa o contrato da validação: linha sem `idempotency_key` tem de
        ser recusada com motivo — nunca aceita em silêncio.
        """
        linha = csv_lote.LinhaLote(numero_linha=2, valor=Decimal("10.00"), descricao="x")

        csv_lote._validar(linha)

        assert linha.valida is False
        assert linha.erro == "idempotency_key vazia"


# ---------------------------------------------------------------------------
# versao.py
# ---------------------------------------------------------------------------
def test_versao_local_quando_o_pacote_nao_esta_instalado(monkeypatch) -> None:
    """Rodar direto do código precisa dar versão reconhecível, não explodir no import."""
    from app import versao as modulo

    def ausente(nome: str) -> str:
        raise importlib.metadata.PackageNotFoundError(nome)

    monkeypatch.setattr(importlib.metadata, "version", ausente)
    try:
        recarregado = importlib.reload(modulo)
        assert recarregado.APP_VERSION == "0.0.0+local"
    finally:
        monkeypatch.undo()
        importlib.reload(modulo)


# ---------------------------------------------------------------------------
# webhooks/assinatura.py
# ---------------------------------------------------------------------------
def test_parte_sem_igual_no_cabecalho_e_ignorada() -> None:
    """Cabeçalho com lixo extra não pode invalidar assinatura legítima."""
    segredo = b"segredo"
    corpo = b'{"evento":"nfse.autorizada"}'
    momento = int(time.time())
    valor = assinatura.assinar(segredo, corpo, timestamp=momento)

    assinatura.verificar(segredo, corpo, f"t={momento},v1={valor},lixo", agora=momento)


# ---------------------------------------------------------------------------
# worker/dlq.py
# ---------------------------------------------------------------------------
class TestDlqItemInexistente:
    async def test_marcar_replay_falhou_de_item_inexistente(self, sessao_db) -> None:
        tenant = _criar_tenant(sessao_db, "dlq-x1")
        await sessao_db.flush()

        with pytest.raises(dlq.ErroDLQ, match="não encontrado"):
            await dlq.marcar_replay_falhou(
                sessao_db, tenant_id=tenant.id, item_id=uuid.uuid4(), erro="SEFAZ fora"
            )

    async def test_descartar_item_inexistente(self, sessao_db) -> None:
        tenant = _criar_tenant(sessao_db, "dlq-x2")
        await sessao_db.flush()

        with pytest.raises(dlq.ErroDLQ, match="não encontrado"):
            await dlq.descartar(sessao_db, tenant_id=tenant.id, item_id=uuid.uuid4())
