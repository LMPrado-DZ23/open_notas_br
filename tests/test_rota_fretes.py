"""Rotas de frete (Melhor Envio) — contrato de recusa e cotação, com dublês.

Cinco desfechos que o integrador precisa distinguir:

- **503** integração não configurada (faltam `client_id`/`redirect_uri`);
- **400** callback com `error`, sem `code`/`state` ou `state` inválido;
- **502** Melhor Envio recusou a troca de código ou a cotação;
- **409** tenant não autorizado a cotar;
- **422** sem CEP de origem.

Nenhuma chamada de rede: o serviço é dublado.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.api.v1 import fretes as rota
from app.core.config import Settings
from app.frete import service as frete_service
from fastapi import HTTPException

TENANT = SimpleNamespace(id=uuid.uuid4())


class DbFalsa:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def execute(self, consulta: object) -> ResultadoFalso:
        return ResultadoFalso()

    async def scalar(self, consulta: object):
        return None


class ResultadoFalso:
    def scalars(self) -> ResultadoFalso:
        return self

    def first(self):
        return None


def _settings(**overrides) -> Settings:
    base = dict(
        environment="test",
        nfse_adapter="mock",
        melhor_envio_client_id="id",
        melhor_envio_redirect_uri="https://app/callback",
        melhor_envio_sandbox=True,
    )
    base.update(overrides)
    return Settings(**base)


class TestIniciar:
    async def test_sem_configuracao_vira_503(self) -> None:
        with pytest.raises(HTTPException) as erro:
            await rota.iniciar_autorizacao(
                TENANT, _settings(melhor_envio_client_id="", melhor_envio_redirect_uri="")
            )

        assert erro.value.status_code == 503
        assert "não configurada" in erro.value.detail

    async def test_devolve_url_com_state_e_escopos(self, monkeypatch) -> None:
        monkeypatch.setattr(frete_service, "gerar_estado", lambda tenant_id, conf: "state-assinado")

        saida = await rota.iniciar_autorizacao(TENANT, _settings())

        assert "state=state-assinado" in saida.url
        assert saida.expira_em_minutos >= 1
        assert saida.escopos


class TestCallback:
    async def test_lojista_recusou_vira_400(self) -> None:
        with pytest.raises(HTTPException) as erro:
            await rota.callback_oauth(
                None,
                code=None,
                state=None,
                error="access_denied",
                db=DbFalsa(),
                settings=_settings(),
            )

        assert erro.value.status_code == 400
        assert "access_denied" in erro.value.detail

    async def test_sem_code_e_state_vira_400(self) -> None:
        with pytest.raises(HTTPException) as erro:
            await rota.callback_oauth(
                None, code="c", state=None, error=None, db=DbFalsa(), settings=_settings()
            )

        assert erro.value.status_code == 400
        assert "obrigatórios" in erro.value.detail

    async def test_state_invalido_vira_400(self, monkeypatch) -> None:
        def ler(state, settings):
            raise frete_service.EstadoInvalido("state expirado")

        monkeypatch.setattr(frete_service, "ler_estado", ler)

        with pytest.raises(HTTPException) as erro:
            await rota.callback_oauth(
                None, code="c", state="s", error=None, db=DbFalsa(), settings=_settings()
            )

        assert erro.value.status_code == 400
        assert "expirado" in erro.value.detail

    async def test_melhor_envio_recusa_vira_502(self, monkeypatch) -> None:
        monkeypatch.setattr(frete_service, "ler_estado", lambda state, settings: uuid.uuid4())

        def trocar(code, sandbox, settings):
            raise frete_service.ErroDeFrete("invalid_grant")

        monkeypatch.setattr(frete_service, "trocar_codigo_por_token", trocar)

        with pytest.raises(HTTPException) as erro:
            await rota.callback_oauth(
                None, code="c", state="s", error=None, db=DbFalsa(), settings=_settings()
            )

        assert erro.value.status_code == 502
        assert "invalid_grant" in erro.value.detail

    async def test_sucesso_salva_e_commita(self, monkeypatch) -> None:
        monkeypatch.setattr(frete_service, "ler_estado", lambda state, settings: TENANT.id)
        monkeypatch.setattr(frete_service, "trocar_codigo_por_token", lambda *a: {"token": "x"})
        credencial = SimpleNamespace(
            sandbox=True,
            expira_em=datetime.now(UTC) + timedelta(hours=1),
            renovado_em=datetime.now(UTC),
            escopo="shipping-calculate",
        )
        monkeypatch.setattr(frete_service, "salvar", lambda *a, **k: _async(credencial))
        db = DbFalsa()

        saida = await rota.callback_oauth(
            None, code="c", state="s", error=None, db=db, settings=_settings()
        )

        assert saida.autorizado is True
        assert saida.sandbox is True
        assert db.commits == 1


class TestStatus:
    async def test_sem_credencial_nao_autorizado(self, monkeypatch) -> None:
        monkeypatch.setattr(frete_service, "por_tenant", lambda *a: _async(None))

        saida = await rota.status_frete(TENANT, DbFalsa())

        assert saida.autorizado is False
        assert "oauth/iniciar" in saida.proximo_passo

    async def test_vencido_com_refresh_continua_autorizado(self, monkeypatch) -> None:
        credencial = SimpleNamespace(
            ativo=True,
            sandbox=True,
            expira_em=datetime.now(UTC) - timedelta(hours=1),
            renovado_em=None,
            refresh_token_selado="selado",
            escopo="shipping-calculate",
        )
        monkeypatch.setattr(frete_service, "por_tenant", lambda *a: _async(credencial))

        saida = await rota.status_frete(TENANT, DbFalsa())

        assert saida.autorizado is True
        assert "renovado na próxima" in saida.proximo_passo

    async def test_vencido_sem_refresh_fica_nao_autorizado(self, monkeypatch) -> None:
        credencial = SimpleNamespace(
            ativo=True,
            sandbox=True,
            expira_em=datetime.now(UTC) - timedelta(hours=1),
            renovado_em=None,
            refresh_token_selado=None,
            escopo=None,
        )
        monkeypatch.setattr(frete_service, "por_tenant", lambda *a: _async(credencial))

        assert (await rota.status_frete(TENANT, DbFalsa())).autorizado is False


class TestRevogar:
    async def test_commit_e_observacao(self, monkeypatch) -> None:
        monkeypatch.setattr(frete_service, "revogar", lambda *a: _async(True))
        db = DbFalsa()

        saida = await rota.revogar(TENANT, db)

        assert saida["revogado"] is True
        assert "painel deles" in saida["observacao"]
        assert db.commits == 1


class TestCotar:
    async def test_sem_cep_vira_422(self, monkeypatch) -> None:
        monkeypatch.setattr(rota, "_cep_da_config", lambda *a: _async(None))
        dados = SimpleNamespace(cep_origem=None, itens=[])

        with pytest.raises(HTTPException) as erro:
            await rota.cotar(dados, TENANT, DbFalsa(), _settings())

        assert erro.value.status_code == 422
        assert "cep_origem" in erro.value.detail

    async def test_nao_autorizado_vira_409(self, monkeypatch) -> None:
        monkeypatch.setattr(rota, "_cep_da_config", lambda *a: _async("72900000"))

        async def cliente_para(*a):
            raise frete_service.NaoAutorizado("sem autorização")

        monkeypatch.setattr(frete_service, "cliente_para", cliente_para)
        dados = SimpleNamespace(cep_origem="72900000", cep_destino="01001000", itens=[])

        with pytest.raises(HTTPException) as erro:
            await rota.cotar(dados, TENANT, DbFalsa(), _settings())

        assert erro.value.status_code == 409

    async def test_erro_de_configuracao_vira_503(self, monkeypatch) -> None:
        monkeypatch.setattr(rota, "_cep_da_config", lambda *a: _async("72900000"))

        async def cliente_para(*a):
            raise frete_service.ErroDeFrete("sem chave")

        monkeypatch.setattr(frete_service, "cliente_para", cliente_para)
        dados = SimpleNamespace(cep_origem="72900000", cep_destino="01001000", itens=[])

        with pytest.raises(HTTPException) as erro:
            await rota.cotar(dados, TENANT, DbFalsa(), _settings())

        assert erro.value.status_code == 503

    async def test_cotacao_bem_sucedida_marca_mais_barata(self, monkeypatch) -> None:

        monkeypatch.setattr(rota, "_cep_da_config", lambda *a: _async("72900000"))
        barata = SimpleNamespace(
            servico_id=1,
            transportadora="A",
            servico="Economico",
            preco="10.00",
            prazo_dias=5,
            moeda="BRL",
        )
        rapida = SimpleNamespace(
            servico_id=2,
            transportadora="B",
            servico="Expresso",
            preco="20.00",
            prazo_dias=1,
            moeda="BRL",
        )
        cotacao = SimpleNamespace(
            disponiveis=[barata, rapida], mais_barata=barata, mais_rapida=rapida
        )

        class ClienteFalso:
            def cotar(self, **kwargs):
                return cotacao

        monkeypatch.setattr(frete_service, "cliente_para", lambda *a: _async(ClienteFalso()))
        dados = SimpleNamespace(cep_origem="72900000", cep_destino="01001000", itens=[])

        saida = await rota.cotar(dados, TENANT, DbFalsa(), _settings())

        assert len(saida.opcoes) == 2
        assert saida.mais_barata.servico_id == 1
        assert saida.mais_rapida.servico_id == 2

    async def test_erro_de_cotacao_vira_502(self, monkeypatch) -> None:
        from app.frete.client import ErroDeCotacao

        monkeypatch.setattr(rota, "_cep_da_config", lambda *a: _async("72900000"))

        class ClienteFalso:
            def cotar(self, **kwargs):
                raise ErroDeCotacao("serviço indisponível")

        monkeypatch.setattr(frete_service, "cliente_para", lambda *a: _async(ClienteFalso()))
        dados = SimpleNamespace(cep_origem="72900000", cep_destino="01001000", itens=[])

        with pytest.raises(HTTPException) as erro:
            await rota.cotar(dados, TENANT, DbFalsa(), _settings())

        assert erro.value.status_code == 502


async def _async(valor):
    return valor


class TestCepDaConfig:
    async def test_sem_configuracao_devolve_none(self) -> None:
        assert await rota._cep_da_config(DbFalsa(), uuid.uuid4()) is None

    async def test_configuracao_com_cep_devolve(self) -> None:
        config = SimpleNamespace(extra={"cep": "72900000"})

        class DbComConfig(DbFalsa):
            async def execute(self, consulta: object):
                return ResultadoConfig(config)

        assert await rota._cep_da_config(DbComConfig(), uuid.uuid4()) == "72900000"

    async def test_configuracao_sem_extra_devolve_none(self) -> None:
        config = SimpleNamespace(extra=None)

        class DbComConfig(DbFalsa):
            async def execute(self, consulta: object):
                return ResultadoConfig(config)

        assert await rota._cep_da_config(DbComConfig(), uuid.uuid4()) is None


class ResultadoConfig:
    def __init__(self, config) -> None:
        self._config = config

    def scalars(self) -> ResultadoConfig:
        return self

    def first(self):
        return self._config
