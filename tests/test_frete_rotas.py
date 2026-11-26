"""Rotas de frete e cofre de token do Melhor Envio.

O que se verifica aqui é o que quebra em produção: `state` forjado, token vencido,
token de outro tenant (o `aad` do cofre) e autorização ausente.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.core.config import Settings
from app.frete import service as frete_service

CONF = Settings(
    environment="test",
    melhor_envio_client_id="9001778",
    melhor_envio_client_secret="segredo",
    melhor_envio_redirect_uri="http://127.0.0.1:8081/v1/fretes/oauth/callback",
    melhor_envio_sandbox=True,
)


class TestEstado:
    def test_ida_e_volta(self) -> None:
        tenant = uuid.uuid4()
        estado = frete_service.gerar_estado(tenant, CONF)
        assert frete_service.ler_estado(estado, CONF) == tenant

    def test_state_forjado_recusado(self) -> None:
        tenant = uuid.uuid4()
        estado = frete_service.gerar_estado(tenant, CONF)
        partes = estado.split(".")
        partes[0] = str(uuid.uuid4())  # troca o tenant, mantém a assinatura
        with pytest.raises(frete_service.EstadoInvalido, match="assinatura"):
            frete_service.ler_estado(".".join(partes), CONF)

    def test_state_de_outra_chave_recusado(self) -> None:
        tenant = uuid.uuid4()
        estado = frete_service.gerar_estado(tenant, CONF)
        import base64

        outra = Settings(
            environment="test",
            master_encryption_key=base64.b64encode(b"z" * 32).decode(),
        )
        with pytest.raises(frete_service.EstadoInvalido):
            frete_service.ler_estado(estado, outra)

    def test_state_expirado_recusado(self) -> None:
        tenant = uuid.uuid4()
        payload = f"{tenant}.{int(time.time()) - frete_service.VALIDADE_ESTADO - 10}"
        estado = f"{payload}.{frete_service._assinar(payload, CONF)}"
        with pytest.raises(frete_service.EstadoInvalido, match="expirado"):
            frete_service.ler_estado(estado, CONF)

    def test_state_malformado(self) -> None:
        with pytest.raises(frete_service.EstadoInvalido, match="malformado"):
            frete_service.ler_estado("abc", CONF)

    def test_state_vazio(self) -> None:
        with pytest.raises(frete_service.EstadoInvalido):
            frete_service.ler_estado("", CONF)


@pytest.fixture
async def tenant_db(sessao_db):
    """Tenant real: a credencial tem FK para tenants, então UUID solto não serve."""
    from app.db.models.tenant import Tenant

    t = Tenant(
        slug=f"frete-{uuid.uuid4().hex[:8]}",
        nome="Frete LTDA",
        api_key_prefix=uuid.uuid4().hex[:8],
        api_key_hash=uuid.uuid4().hex,
    )
    sessao_db.add(t)
    await sessao_db.flush()
    return t.id


class TestCofreDoToken:
    async def test_token_selado_nao_fica_em_claro(self, sessao_db, tenant_db) -> None:
        from app.db.models.frete import FreteCredencial
        from app.frete.oauth import TokenOAuth

        tenant = tenant_db
        token = TokenOAuth(
            access_token="TOKEN-SUPER-SECRETO",
            refresh_token="REFRESH-SECRETO",
            expira_em=datetime.now(UTC) + timedelta(days=30),
        )
        credencial = await frete_service.salvar(
            sessao_db, tenant, token, sandbox=True, settings=CONF
        )
        assert b"TOKEN-SUPER-SECRETO" not in credencial.access_token_selado
        assert b"REFRESH-SECRETO" not in (credencial.refresh_token_selado or b"")
        assert isinstance(credencial, FreteCredencial)

    async def test_blob_de_outro_tenant_nao_abre(self, sessao_db, tenant_db) -> None:
        from app.core.crypto import Cofre, aad_do_tenant
        from app.frete.oauth import TokenOAuth

        tenant = tenant_db
        token = TokenOAuth(access_token="abc", refresh_token="def", expira_em=datetime.now(UTC))
        credencial = await frete_service.salvar(
            sessao_db, tenant, token, sandbox=True, settings=CONF
        )
        cofre = Cofre(CONF.master_key())
        # Mesmo blob, outro tenant: o AAD impede a abertura.
        from app.core.crypto import ErroDeCriptografia

        with pytest.raises(ErroDeCriptografia):
            cofre.abrir(credencial.access_token_selado, aad=aad_do_tenant(uuid.uuid4()))

    async def test_revogar_apaga_os_tokens(self, sessao_db, tenant_db) -> None:
        from app.frete.oauth import TokenOAuth

        tenant = tenant_db
        await frete_service.salvar(
            sessao_db,
            tenant,
            TokenOAuth(access_token="a", refresh_token="b", expira_em=None),
            sandbox=True,
            settings=CONF,
        )
        assert await frete_service.revogar(sessao_db, tenant) is True
        credencial = await frete_service.por_tenant(sessao_db, tenant)
        assert credencial is not None
        assert credencial.ativo is False
        assert credencial.access_token_selado == b""
        assert credencial.refresh_token_selado is None

    async def test_revogar_sem_credencial(self, sessao_db) -> None:
        assert await frete_service.revogar(sessao_db, uuid.uuid4()) is False


class TestCliente:
    async def test_sem_credencial_nao_autoriza(self, sessao_db) -> None:
        with pytest.raises(frete_service.NaoAutorizado, match="autorizou"):
            await frete_service.cliente_para(sessao_db, uuid.uuid4(), CONF)

    async def test_token_valido_entrega_cliente(self, sessao_db, tenant_db) -> None:
        from app.frete.oauth import TokenOAuth

        tenant = tenant_db
        await frete_service.salvar(
            sessao_db,
            tenant,
            TokenOAuth(
                access_token="valido",
                refresh_token="r",
                expira_em=datetime.now(UTC) + timedelta(days=10),
            ),
            sandbox=True,
            settings=CONF,
        )
        cliente = await frete_service.cliente_para(sessao_db, tenant, CONF)
        assert cliente is not None

    async def test_token_vencido_sem_refresh_pede_autorizacao(self, sessao_db, tenant_db) -> None:
        from app.frete.oauth import TokenOAuth

        tenant = tenant_db
        # Salva uma vez e depois zera o refresh para simular credencial antiga:
        # `salvar` faz upsert, então chamar de novo geraria outra linha.
        await frete_service.salvar(
            sessao_db,
            tenant,
            TokenOAuth(
                access_token="velho",
                refresh_token=None,
                expira_em=datetime.now(UTC) - timedelta(days=1),
            ),
            sandbox=True,
            settings=CONF,
        )
        credencial = await frete_service.por_tenant(sessao_db, tenant)
        credencial.refresh_token_selado = None
        await sessao_db.flush()
        with pytest.raises(frete_service.NaoAutorizado, match="refaça a autorização"):
            await frete_service.cliente_para(sessao_db, tenant, CONF)


class TestSemCredenciaisDoApp:
    def test_sem_client_id_da_erro_claro(self) -> None:
        # Passar os campos vazios de propósito: sem isso o `Settings` lê o `.env`
        # local, que tem credencial real, e o teste faria chamada de verdade à API
        # do Melhor Envio com um `code` inventado.
        vazia = Settings(
            environment="test", melhor_envio_client_id="", melhor_envio_client_secret=""
        )
        with pytest.raises(frete_service.ErroDeFrete, match="MELHOR_ENVIO_CLIENT_ID"):
            frete_service.trocar_codigo_por_token("code", True, vazia)


class TestCotacaoSchema:
    def test_item_exige_dimensoes_positivas(self) -> None:
        import pydantic
        from app.api.v1.fretes import ItemCarrinho

        with pytest.raises(pydantic.ValidationError):
            ItemCarrinho(
                peso_kg=Decimal("0"),
                altura_cm=Decimal("10"),
                largura_cm=Decimal("10"),
                comprimento_cm=Decimal("10"),
                valor=Decimal("10"),
            )

    def test_carrinho_vazio_recusado(self) -> None:
        import pydantic
        from app.api.v1.fretes import CotacaoIn

        with pytest.raises(pydantic.ValidationError):
            CotacaoIn(cep_destino="01001000", itens=[])
