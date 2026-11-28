"""Rotação de chave: `[]` significa NENHUM escopo, não "sem restrição".

Antes, `app/tenants/service.py` gravava `escopos or None`: pedir lista vazia (nenhum escopo) virava
`None`, que `app/api/deps.py` interpreta como **sem restrição**. Fail-open: a chave mais restrita
pedida era a mais ampla entregue.

Agora `None`/omitido continua amplo (compatibilidade das chaves legadas) e `[]` nega tudo.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.api import deps
from app.tenants import service


class SessaoFalsa:
    def __init__(self) -> None:
        self.flushes = 0

    async def flush(self) -> None:
        self.flushes += 1


def _tenant() -> SimpleNamespace:
    return SimpleNamespace(
        api_key_prefix=None,
        api_key_hash=None,
        api_key_rotacionada_em=None,
        api_key_revogada_em=None,
        api_key_expira_em=None,
        api_key_escopos=None,
    )


async def _rotacionar(monkeypatch, escopos):
    tenant = _tenant()

    async def por_id(sessao, tenant_id):
        return tenant

    monkeypatch.setattr(service.repo, "por_id", por_id)

    _, chave = await service.rotacionar_chave(SessaoFalsa(), uuid.uuid4(), escopos=escopos)
    return tenant, chave


class TestRotacao:
    async def test_lista_vazia_grava_lista_vazia(self, monkeypatch) -> None:
        tenant, _ = await _rotacionar(monkeypatch, [])

        assert tenant.api_key_escopos == [], "lista vazia não pode virar None (fail-open)"

    async def test_omitido_continua_amplo(self, monkeypatch) -> None:
        tenant, _ = await _rotacionar(monkeypatch, None)

        assert tenant.api_key_escopos is None, "chave legada sem escopo precisa seguir funcionando"

    async def test_lista_com_escopo_e_preservada(self, monkeypatch) -> None:
        tenant, _ = await _rotacionar(monkeypatch, ["leitura"])

        assert tenant.api_key_escopos == ["leitura"]

    async def test_rotacao_limpa_revogacao_e_gera_chave(self, monkeypatch) -> None:
        tenant, chave = await _rotacionar(monkeypatch, ["emissao"])

        assert chave.startswith(("nbr_", "ok_")) or len(chave) > 20
        assert tenant.api_key_revogada_em is None


class TestEnforcement:
    def test_lista_vazia_nega_leitura_e_emissao(self) -> None:
        tenant = SimpleNamespace(api_key_escopos=[])

        for metodo in ("GET", "POST"):
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as erro:
                deps._exigir_escopo(tenant, metodo)
            assert "escopo" in str(erro.value).lower()

    def test_sem_restricao_permite(self) -> None:
        deps._exigir_escopo(SimpleNamespace(api_key_escopos=None), "POST")

    def test_escopo_presente_permite(self) -> None:
        deps._exigir_escopo(SimpleNamespace(api_key_escopos=["leitura"]), "GET")

    def test_escopo_ausente_nega(self) -> None:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as erro:
            deps._exigir_escopo(SimpleNamespace(api_key_escopos=["leitura"]), "POST")

        assert erro.value.status_code == 403
