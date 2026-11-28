"""Entrega de webhook: segredo ilegível, segredo ausente e isolamento por entrega.

Três falhas que já aconteceram em operação e precisam de desfecho próprio:

- segredo **selado com outra chave-mestra** (backup restaurado, chave trocada): não há como abrir, e
  retentar para sempre só consome fila — o registro vira `FALHOU` com instrução de rotação;
- tenant **sem segredo**: entrega não pode ficar pendente eternamente;
- exceção inesperada em **uma** entrega não pode travar a fila dos outros tenants.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.db.models.enums import StatusWebhook
from app.webhooks import service


class SessaoFalsa:
    def __init__(self, tenant=None, entregas=None) -> None:
        self._tenant = tenant
        self._entregas = entregas or []
        self.adicionados: list = []
        self.flushes = 0

    def add(self, objeto: object) -> None:
        self.adicionados.append(objeto)

    async def flush(self) -> None:
        self.flushes += 1

    async def execute(self, consulta: object):
        return ResultadoFalso(self._tenant if self._tenant is not None else self._entregas)

    async def get(self, modelo: object, pk: object):
        return self._tenant


class ResultadoFalso:
    def __init__(self, item) -> None:
        self._item = item

    def scalar_one_or_none(self):
        return self._item

    def scalars(self) -> ResultadoFalso:
        return self

    def all(self) -> list:
        return self._item if isinstance(self._item, list) else [self._item]

    def first(self):
        if isinstance(self._item, list):
            return self._item[0] if self._item else None
        return self._item


def _tenant(**extra) -> SimpleNamespace:
    base = dict(id=uuid.uuid4(), webhook_secret_selado=None, webhook_url=None)
    base.update(extra)
    return SimpleNamespace(**base)


def _entrega(tenant=None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=(tenant or _tenant()).id,
        tipo_evento="nfse.autorizada",
        payload={"chave": "1" * 44},
        status=StatusWebhook.PENDENTE,
        tentativas=0,
        proxima_tentativa=None,
        ultimo_erro=None,
        codigo_http=None,
        url_destino="https://cliente.example/webhook",
    )


class TestObterSegredo:
    def test_tenant_sem_segredo_devolve_none(self) -> None:
        assert service.obter_segredo(_tenant()) is None


class TestEntregarSemSegredo:
    async def test_tenant_sem_segredo_marca_falha(self, monkeypatch) -> None:
        tenant = _tenant()
        entrega = _entrega(tenant)
        sessao = SessaoFalsa(tenant=tenant)

        await service.entregar(sessao, entrega)

        assert entrega.status is StatusWebhook.FALHOU
        assert "sem segredo" in entrega.ultimo_erro
        assert sessao.flushes == 1

    async def test_segredo_ilegivel_manda_rotacionar(self, monkeypatch) -> None:
        """Segredo selado com outra chave-mestra não é retentável: instrução é rotacionar."""
        tenant = _tenant(webhook_secret_selado=b"selado")
        entrega = _entrega(tenant)
        sessao = SessaoFalsa(tenant=tenant)

        def explodir(t):
            raise ValueError("chave errada")

        monkeypatch.setattr(service, "obter_segredo", explodir)

        await service.entregar(sessao, entrega)

        assert entrega.status is StatusWebhook.FALHOU
        assert "rotacione" in entrega.ultimo_erro
        assert "ValueError" in entrega.ultimo_erro


class TestProcessarPendentes:
    async def test_excecao_em_uma_entrega_nao_trava_as_outras(self, monkeypatch) -> None:
        primeira = _entrega()
        segunda = _entrega()
        sessao = SessaoFalsa(entregas=[primeira, segunda])
        vistas: list = []

        async def entregar_falso(sessao_, entrega, cliente=None):
            vistas.append(entrega.id)
            if entrega is primeira:
                raise RuntimeError("boom")
            entrega.status = StatusWebhook.ENTREGUE
            return entrega

        monkeypatch.setattr(service, "entregar", entregar_falso)

        contagem = await service.processar_pendentes(sessao)

        assert vistas == [primeira.id, segunda.id], "a segunda entrega precisa ser tentada"
        assert primeira.status is StatusWebhook.FALHOU
        assert "erro inesperado" in primeira.ultimo_erro
        assert contagem["entregues"] == 1


class TestFalhaDeRede:
    async def test_httperror_registra_falha_e_nao_derruba(self, monkeypatch) -> None:
        """Falha de rede é retentável: registra o motivo e devolve a entrega (sem exceção)."""
        import httpx

        tenant = _tenant(webhook_secret_selado=b"selado")
        entrega = _entrega(tenant)
        sessao = SessaoFalsa(tenant=tenant)
        monkeypatch.setattr(service, "obter_segredo", lambda t: b"segredo-de-teste")

        class ClienteQueCai:
            async def post(self, url, **kwargs):
                raise httpx.ConnectError("sem rota")

        await service.entregar(sessao, entrega, cliente=ClienteQueCai())

        # Falha de rede é retentável: a entrega continua pendente com nova tentativa agendada.
        assert entrega.status is StatusWebhook.PENDENTE
        assert entrega.tentativas >= 1
        assert "falha de rede" in entrega.ultimo_erro
        assert "ConnectError" in entrega.ultimo_erro
