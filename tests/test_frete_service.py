"""Frete: state assinado, troca de código e renovação de token.

O `state` do OAuth é a única coisa que impede um callback forjado de ligar a conta do atacante ao
tenant da vítima. Ele é assinado com HMAC da chave-mestra, carrega o tenant e **expira em 15 minutos**.
Cada uma dessas três propriedades tem teste.

Sem rede: `trocar_codigo` e `renovar` são dublados.
"""

from __future__ import annotations

import base64
import time
import uuid
from types import SimpleNamespace

import pytest
from app.core.config import Settings
from app.frete import service


def _settings(**overrides) -> Settings:
    base = dict(
        environment="test",
        nfse_adapter="mock",
        master_encryption_key=base64.b64encode(b"k" * 32).decode(),
        melhor_envio_client_id="id",
        melhor_envio_client_secret="secret",
        melhor_envio_redirect_uri="https://app/callback",
    )
    base.update(overrides)
    return Settings(**base)


class TestState:
    def test_ida_e_volta_devolve_o_tenant(self) -> None:
        tenant = uuid.uuid4()

        state = service.gerar_estado(tenant, _settings())

        assert service.ler_estado(state, _settings()) == tenant

    def test_state_forjado_recusa(self) -> None:
        original = service.gerar_estado(uuid.uuid4(), _settings())
        _tenant, carimbo, _ = original.split(".")

        with pytest.raises(service.EstadoInvalido) as erro:
            service.ler_estado(f"{uuid.uuid4()}.{carimbo}.{_assinatura_falsa()}", _settings())

        assert "assinatura inválida" in str(erro.value) or "inválido" in str(erro.value)

    def test_state_de_outro_segredo_recusa(self) -> None:
        state = service.gerar_estado(uuid.uuid4(), _settings())

        with pytest.raises(service.EstadoInvalido):
            service.ler_estado(
                state, _settings(master_encryption_key=base64.b64encode(b"x" * 32).decode())
            )

    def test_carimbo_nao_numerico_recusa(self) -> None:
        tenant = uuid.uuid4()
        settings = _settings()
        assinatura = service._assinar(f"{tenant}.abc", settings)

        with pytest.raises(service.EstadoInvalido) as erro:
            service.ler_estado(f"{tenant}.abc.{assinatura}", settings)

        assert "carimbo" in str(erro.value)

    def test_state_expirado_recusa(self) -> None:
        tenant = uuid.uuid4()
        settings = _settings()
        antigo = str(int(time.time()) - service.VALIDADE_ESTADO - 60)
        assinatura = service._assinar(f"{tenant}.{antigo}", settings)

        with pytest.raises(service.EstadoInvalido) as erro:
            service.ler_estado(f"{tenant}.{antigo}.{assinatura}", settings)

        assert "expirado" in str(erro.value)

    def test_tenant_invalido_recusa(self) -> None:
        settings = _settings()
        carimbo = str(int(time.time()))
        assinatura = service._assinar(f"nao-e-uuid.{carimbo}", settings)

        with pytest.raises(service.EstadoInvalido) as erro:
            service.ler_estado(f"nao-e-uuid.{carimbo}.{assinatura}", settings)

        assert "tenant" in str(erro.value)


def _assinatura_falsa() -> str:
    return "0" * 64


class TestTrocaDeCodigo:
    def test_sem_credenciais_configuradas_recusa(self) -> None:
        with pytest.raises(service.ErroDeFrete) as erro:
            service.trocar_codigo_por_token(
                "code",
                sandbox=True,
                settings=_settings(melhor_envio_client_id="", melhor_envio_client_secret=""),
            )

        assert "não configurados" in str(erro.value)

    def test_com_credenciais_delega(self, monkeypatch) -> None:
        visto: dict = {}

        def trocar(**kwargs):
            visto.update(kwargs)
            return {"access_token": "a"}

        monkeypatch.setattr(service, "trocar_codigo", trocar)

        assert service.trocar_codigo_por_token("code", sandbox=True, settings=_settings()) == {
            "access_token": "a"
        }
        assert visto["client_id"] == "id" and visto["sandbox"] is True


class TestTokenValido:
    async def test_credencial_inativa_recusa(self) -> None:
        credencial = SimpleNamespace(ativo=False, tenant_id=uuid.uuid4())

        with pytest.raises(service.NaoAutorizado) as erro:
            await service._token_valido(None, credencial, _settings())

        assert "oauth/iniciar" in str(erro.value)

    async def test_vencido_sem_refresh_recusa(self) -> None:
        from datetime import UTC, datetime, timedelta

        settings = _settings()
        tenant_id = uuid.uuid4()
        # O token de acesso precisa abrir de verdade: o cofre valida o envelope antes do refresh.
        selado = service._cofre(settings).selar(
            b"access-token", aad=service.aad_do_tenant(tenant_id)
        )
        credencial = SimpleNamespace(
            ativo=True,
            tenant_id=tenant_id,
            expira_em=datetime.now(UTC) - timedelta(hours=1),
            access_token_selado=selado,
            refresh_token_selado=None,
            sandbox=True,
        )

        with pytest.raises(service.NaoAutorizado) as erro:
            await service._token_valido(None, credencial, settings)

        assert "refaça a autorização" in str(erro.value)


class TestRevogar:
    async def test_sem_credencial_devolve_false(self, monkeypatch) -> None:
        async def nada(*a):
            return None

        monkeypatch.setattr(service, "por_tenant", nada)

        assert await service.revogar(None, uuid.uuid4()) is False
