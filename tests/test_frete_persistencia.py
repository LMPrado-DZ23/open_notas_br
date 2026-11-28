"""Persistência da credencial de frete: selar, revogar (apagando token) e montar cliente.

Regras que o teste protege:

- `salvar` **sela** os tokens com `aad` do tenant — blob de uma loja não abre em outra;
- `salvar` em tenant que já tem credencial **atualiza**, não duplica;
- `revogar` apaga o token selado (`b""`) e o refresh (`None`) — não basta marcar inativo;
- `cliente_para` sem credencial recusa com o caminho de autorização.
"""

from __future__ import annotations

import base64
import uuid
from types import SimpleNamespace

import pytest
from app.core.config import Settings
from app.frete import service
from app.frete.client import MelhorEnvioClient


def _settings() -> Settings:
    return Settings(
        environment="test",
        nfse_adapter="mock",
        master_encryption_key=base64.b64encode(b"k" * 32).decode(),
        melhor_envio_client_id="id",
        melhor_envio_client_secret="secret",
    )


class ResultadoFalso:
    def __init__(self, item) -> None:
        self._item = item

    def scalars(self) -> ResultadoFalso:
        return self

    def first(self):
        return self._item


class SessaoFalsa:
    def __init__(self, existente=None) -> None:
        self._existente = existente
        self.adicionados: list = []
        self.flushes = 0

    def add(self, objeto: object) -> None:
        self.adicionados.append(objeto)

    async def flush(self) -> None:
        self.flushes += 1

    async def execute(self, consulta: object) -> ResultadoFalso:
        return ResultadoFalso(self._existente)


def _token(**extra) -> SimpleNamespace:
    base = dict(
        access_token="access",
        refresh_token="refresh",
        expira_em=None,
        escopo="shipping-calculate",
    )
    base.update(extra)
    return SimpleNamespace(**base)


class TestSalvar:
    async def test_sela_tokens_com_aad_do_tenant(self) -> None:
        settings = _settings()
        tenant_id = uuid.uuid4()
        sessao = SessaoFalsa()

        credencial = await service.salvar(
            sessao, tenant_id, _token(), sandbox=True, settings=settings
        )

        cofre = service._cofre(settings)
        aad = service.aad_do_tenant(tenant_id)
        assert cofre.abrir(credencial.access_token_selado, aad=aad) == b"access"
        assert cofre.abrir(credencial.refresh_token_selado, aad=aad) == b"refresh"
        assert credencial.ativo is True
        assert sessao.adicionados == [credencial]

    async def test_credencial_existente_e_atualizada_sem_duplicar(self) -> None:
        existente = SimpleNamespace(tenant_id=uuid.uuid4(), access_token_selado=b"antigo")
        sessao = SessaoFalsa(existente)

        credencial = await service.salvar(
            sessao, existente.tenant_id, _token(), sandbox=False, settings=_settings()
        )

        assert credencial is existente, "não pode criar segunda credencial para o mesmo tenant"
        assert not sessao.adicionados
        assert credencial.access_token_selado != b"antigo"
        assert credencial.sandbox is False

    async def test_sem_refresh_nao_apaga_o_anterior(self) -> None:
        """Resposta sem `refresh_token` (comum) não pode zerar o refresh já guardado."""
        existente = SimpleNamespace(tenant_id=uuid.uuid4(), refresh_token_selado=b"guardado")
        sessao = SessaoFalsa(existente)

        credencial = await service.salvar(
            sessao,
            existente.tenant_id,
            _token(refresh_token=None),
            sandbox=True,
            settings=_settings(),
        )

        assert credencial.refresh_token_selado == b"guardado"


class TestRevogar:
    async def test_revogar_apaga_os_tokens(self) -> None:
        existente = SimpleNamespace(
            tenant_id=uuid.uuid4(),
            ativo=True,
            access_token_selado=b"selado",
            refresh_token_selado=b"refresh-selado",
            expira_em="2026-12-01T00:00:00",
        )
        sessao = SessaoFalsa(existente)

        assert await service.revogar(sessao, existente.tenant_id) is True
        assert existente.ativo is False
        assert existente.access_token_selado == b""
        assert existente.refresh_token_selado is None
        assert existente.expira_em is None
        assert sessao.flushes == 1


class TestClientePara:
    async def test_sem_credencial_recusa_com_o_caminho(self) -> None:
        with pytest.raises(service.NaoAutorizado) as erro:
            await service.cliente_para(SessaoFalsa(None), uuid.uuid4(), _settings())

        assert "oauth/iniciar" in str(erro.value)

    async def test_com_credencial_monta_cliente(self, monkeypatch) -> None:
        existente = SimpleNamespace(tenant_id=uuid.uuid4(), sandbox=True, ativo=True)

        async def token_valido(sessao, credencial, settings):
            return _token(access_token="token-novo")

        monkeypatch.setattr(service, "_token_valido", token_valido)

        cliente = await service.cliente_para(
            SessaoFalsa(existente), existente.tenant_id, _settings()
        )

        assert isinstance(cliente, MelhorEnvioClient)
