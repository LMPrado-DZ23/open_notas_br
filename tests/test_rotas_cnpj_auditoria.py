"""Rotas de CNPJ e de laudo fiscal — testadas na função, com dublês (sem banco, sem rede).

`app/api/v1/cnpj.py` e `app/api/v1/auditoria.py` concentram decisões de contrato: 422 x 404 x 503,
404 em vez de 403 para laudo de outro tenant, e a serialização do laudo. Nenhuma delas precisa de
PostgreSQL para ser provada — o serviço é substituído.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.api.v1 import auditoria as rota_auditoria
from app.api.v1 import cnpj as rota_cnpj
from app.cnpj.client import CnpjInvalido, CnpjNaoEncontrado, FonteIndisponivel
from app.core.config import Settings
from fastapi import HTTPException


class ServicoCnpjFalso:
    def __init__(self, resultado=None, erro: Exception | None = None) -> None:
        self._resultado = resultado
        self._erro = erro

    async def consultar(self, cnpj: str, *, usar_cache: bool = True):
        if self._erro is not None:
            raise self._erro
        return self._resultado


class ResultadoFalso:
    def to_dict(self) -> dict:
        return {"cnpj": "11222333000181", "razao_social": "ACME"}


def _settings(**overrides) -> Settings:
    return Settings(environment="test", nfse_adapter="mock", **overrides)


class TestMontarServico:
    def test_sem_token_usa_apenas_fontes_publicas(self, monkeypatch) -> None:
        monkeypatch.setattr(rota_cnpj, "obter_redis", lambda: object())

        servico = rota_cnpj.montar_servico(_settings(serpro_cnpj_token=""))

        nomes = [type(f).__name__ for f in servico.fontes]
        assert nomes == ["BrasilApiCnpj", "MinhaReceitaCnpj"]

    def test_com_token_serpro_vem_primeiro(self, monkeypatch) -> None:
        monkeypatch.setattr(rota_cnpj, "obter_redis", lambda: object())

        servico = rota_cnpj.montar_servico(_settings(serpro_cnpj_token="tok"))

        assert type(servico.fontes[0]).__name__ == "SerproCnpj"
        assert type(servico.fontes[1]).__name__ == "BrasilApiCnpj"

    def test_fallback_desligado_sem_token_ainda_usa_publicas(self, monkeypatch) -> None:
        """Sem fonte alguma o serviço não consultaria nada; a pública é o piso."""
        monkeypatch.setattr(rota_cnpj, "obter_redis", lambda: object())

        servico = rota_cnpj.montar_servico(
            _settings(serpro_cnpj_token="", cnpj_fallback_enabled=False)
        )

        assert len(servico.fontes) == 2

    def test_fallback_desligado_com_token_so_serpro(self, monkeypatch) -> None:
        monkeypatch.setattr(rota_cnpj, "obter_redis", lambda: object())

        servico = rota_cnpj.montar_servico(
            _settings(serpro_cnpj_token="tok", cnpj_fallback_enabled=False)
        )

        assert [type(f).__name__ for f in servico.fontes] == ["SerproCnpj"]


class TestRotaCnpj:
    async def _chamar(self, monkeypatch, servico) -> dict:
        monkeypatch.setattr(rota_cnpj, "montar_servico", lambda settings: servico)
        return await rota_cnpj.consultar_cnpj("11222333000181", True, _settings(), object())

    async def test_sucesso_devolve_dict(self, monkeypatch) -> None:
        assert await self._chamar(monkeypatch, ServicoCnpjFalso(ResultadoFalso())) == {
            "cnpj": "11222333000181",
            "razao_social": "ACME",
        }

    async def test_invalido_vira_422(self, monkeypatch) -> None:
        with pytest.raises(HTTPException) as erro:
            await self._chamar(monkeypatch, ServicoCnpjFalso(erro=CnpjInvalido("dv errado")))

        assert erro.value.status_code == 422

    async def test_nao_encontrado_vira_404(self, monkeypatch) -> None:
        with pytest.raises(HTTPException) as erro:
            await self._chamar(monkeypatch, ServicoCnpjFalso(erro=CnpjNaoEncontrado("sumiu")))

        assert erro.value.status_code == 404

    async def test_fonte_fora_vira_503_transitorio(self, monkeypatch) -> None:
        with pytest.raises(HTTPException) as erro:
            await self._chamar(monkeypatch, ServicoCnpjFalso(erro=FonteIndisponivel("caiu")))

        assert erro.value.status_code == 503
        assert erro.value.detail["transitorio"] is True


_TENANT = SimpleNamespace(id=uuid.uuid4())


def _registro(**extra):
    base = {
        "id": uuid.uuid4(),
        "trace_id": "trace-1",
        "versao_formato": "1.0",
        "hash_entrada": "a" * 64,
        "hash_saida": "b" * 64,
        "hash_laudo": "c" * 64,
        "data_emissao": datetime(2026, 11, 28, tzinfo=UTC),
        "regras": ["R1"],
        "tabelas": {"t": 1},
        "entrada": {"x": 1},
        "saida": {"y": 2},
        "created_at": datetime(2026, 11, 28, tzinfo=UTC),
    }
    base.update(extra)
    return SimpleNamespace(**base)


class TestRotaAuditoria:
    async def test_laudo_existente_serializa(self, monkeypatch) -> None:
        registro = _registro()
        monkeypatch.setattr(rota_auditoria.svc, "por_id", lambda *a, **k: _async(registro))

        saida = await rota_auditoria.obter_laudo(registro.id, _TENANT, object())

        assert saida["id"] == str(registro.id)
        assert saida["trace_id"] == "trace-1"
        assert saida["data_emissao"].startswith("2026-11-28")

    async def test_laudo_ausente_vira_404_nao_403(self, monkeypatch) -> None:
        """Laudo de outro tenant tem que parecer inexistente: 403 confirmaria a existência."""
        monkeypatch.setattr(rota_auditoria.svc, "por_id", lambda *a, **k: _async(None))

        with pytest.raises(HTTPException) as erro:
            await rota_auditoria.obter_laudo(uuid.uuid4(), _TENANT, object())

        assert erro.value.status_code == 404

    async def test_data_emissao_nula_nao_explode(self, monkeypatch) -> None:
        registro = _registro(data_emissao=None)
        monkeypatch.setattr(rota_auditoria.svc, "por_id", lambda *a, **k: _async(registro))

        saida = await rota_auditoria.obter_laudo(registro.id, _TENANT, object())

        assert saida["data_emissao"] is None

    async def test_lista_por_trace_conta_itens(self, monkeypatch) -> None:
        registros = [_registro(), _registro()]
        monkeypatch.setattr(rota_auditoria.svc, "por_trace", lambda *a, **k: _async(registros))

        saida = await rota_auditoria.listar_por_trace("trace-1", _TENANT, object())

        assert saida["total"] == 2
        assert len(saida["itens"]) == 2

    async def test_lista_vazia_devolve_zero(self, monkeypatch) -> None:
        monkeypatch.setattr(rota_auditoria.svc, "por_trace", lambda *a, **k: _async([]))

        saida = await rota_auditoria.listar_por_trace("nao-existe", _TENANT, object())

        assert saida == {"itens": [], "total": 0}

    async def test_integridade_verdadeira(self, monkeypatch) -> None:
        registro = _registro()
        monkeypatch.setattr(rota_auditoria.svc, "por_id", lambda *a, **k: _async(registro))
        monkeypatch.setattr(rota_auditoria.svc, "verificar_integridade", lambda r: _async(True))

        saida = await rota_auditoria.verificar_laudo(registro.id, _TENANT, object())

        assert saida["integra"] is True
        assert saida["hash_entrada_gravado"] == "a" * 64

    async def test_integridade_falsa_quando_adulterado(self, monkeypatch) -> None:
        registro = _registro()
        monkeypatch.setattr(rota_auditoria.svc, "por_id", lambda *a, **k: _async(registro))
        monkeypatch.setattr(rota_auditoria.svc, "verificar_integridade", lambda r: _async(False))

        saida = await rota_auditoria.verificar_laudo(registro.id, _TENANT, object())

        assert saida["integra"] is False

    async def test_integridade_de_laudo_ausente_vira_404(self, monkeypatch) -> None:
        monkeypatch.setattr(rota_auditoria.svc, "por_id", lambda *a, **k: _async(None))

        with pytest.raises(HTTPException) as erro:
            await rota_auditoria.verificar_laudo(uuid.uuid4(), _TENANT, object())

        assert erro.value.status_code == 404


async def _async(valor):
    return valor
