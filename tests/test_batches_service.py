"""Processamento de lote — a regra que não pode falhar em silêncio.

Três promessas do módulo, e cada uma tem teste:

1. **linha com problema não para o lote** — as demais são processadas;
2. **relatório é gravado mesmo quando tudo falha** — lote sem relatório não é auditável;
3. **reprocessar não duplica nota** — chave já usada vira "ja_existia".

Sem esses testes, um `continue` esquecido marcaria lote inteiro como falho sem ninguém notar.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.batches import service
from app.batches.csv import LinhaLote, LoteLido
from app.db.models.enums import StatusFatura, StatusLote
from app.db.models.ops import BatchJob


class ResultadoFalso:
    def __init__(self, item=None) -> None:
        self._item = item

    def scalars(self) -> ResultadoFalso:
        return self

    def first(self):
        return self._item

    def all(self) -> list:
        return [] if self._item is None else [self._item]


class SessaoFalsa:
    def __init__(self, existente=None) -> None:
        self._existente = existente
        self.adicionados: list = []
        self.flushes = 0
        self.rollbacks = 0
        self.executadas: list = []

    def add(self, objeto: object) -> None:
        self.adicionados.append(objeto)
        if getattr(objeto, "id", None) is None:
            objeto.id = uuid.uuid4()

    async def flush(self) -> None:
        self.flushes += 1
        for objeto in self.adicionados:
            if getattr(objeto, "id", None) is None:
                objeto.id = uuid.uuid4()

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def execute(self, consulta: object) -> ResultadoFalso:
        self.executadas.append(consulta)
        return ResultadoFalso(self._existente)


def _job() -> BatchJob:
    """Instância real do modelo: `flag_modified` exige estado instrumentado do SQLAlchemy."""
    return BatchJob(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        tipo="nfse",
        status=StatusLote.PENDENTE,
        total_linhas=0,
        processadas=0,
        sucesso=0,
        falhas=0,
        relatorio=[],
    )


def _lote(*linhas: LinhaLote) -> LoteLido:
    return LoteLido(linhas=list(linhas))


def _linha(numero: int = 1, valida: bool = True) -> LinhaLote:
    if not valida:
        return LinhaLote(numero_linha=numero, erro="valor ausente", idempotency_key=f"k{numero}")
    return LinhaLote(
        numero_linha=numero,
        idempotency_key=f"k{numero}",
        valor=Decimal("10.00"),
        descricao="servico",
        tomador_nome="Tomador",
        tomador_documento="11222333000181",
    )


TENANT = SimpleNamespace(id=uuid.uuid4())


class TestCriar:
    async def test_registra_pendente_com_relatorio(self, monkeypatch) -> None:
        lote = _lote(_linha(1), _linha(2, valida=False))
        monkeypatch.setattr(service, "ler_csv", lambda conteudo: lote)
        sessao = SessaoFalsa()

        job, devolvido = await service.criar(sessao, TENANT, nome_arquivo="a.csv", conteudo=b"x")

        assert devolvido is lote
        assert job.status == StatusLote.PENDENTE
        assert job.total_linhas == 2
        assert [r["status"] for r in job.relatorio] == ["pendente", "ignorada"]
        assert sessao.adicionados == [job]

    async def test_nome_longo_e_truncado(self, monkeypatch) -> None:
        monkeypatch.setattr(service, "ler_csv", lambda conteudo: _lote())

        job, _ = await service.criar(SessaoFalsa(), TENANT, nome_arquivo="n" * 400, conteudo=b"x")

        assert len(job.nome_arquivo) == 255


class TestProcessar:
    async def test_linha_invalida_nao_interrompe(self, monkeypatch) -> None:
        lote = _lote(_linha(1), _linha(2, valida=False), _linha(3))
        chamadas: list[int] = []

        async def processar_linha(sessao, tenant, linha, **kwargs):
            chamadas.append(linha.numero_linha)
            return {"linha": linha.numero_linha, "status": "autorizado"}

        monkeypatch.setattr(service, "_processar_linha", processar_linha)
        job = _job()

        await service.processar(SessaoFalsa(), job, lote, TENANT)

        assert chamadas == [1, 3], "linha inválida não pode chegar ao emissor"
        assert job.sucesso == 2 and job.falhas == 1
        assert job.status == StatusLote.PARCIAL

    async def test_tudo_autorizado_vira_concluido(self, monkeypatch) -> None:
        lote = _lote(_linha(1), _linha(2))

        async def processar_linha(sessao, tenant, linha, **kwargs):
            return {"linha": linha.numero_linha, "status": "autorizado"}

        monkeypatch.setattr(service, "_processar_linha", processar_linha)
        job = _job()

        await service.processar(SessaoFalsa(), job, lote, TENANT)

        assert job.status == StatusLote.CONCLUIDO
        assert job.processadas == 2
        assert job.finalizado_em is not None

    async def test_relatorio_gravado_mesmo_com_tudo_falhando(self, monkeypatch) -> None:
        lote = _lote(_linha(1), _linha(2))

        async def processar_linha(sessao, tenant, linha, **kwargs):
            return {"linha": linha.numero_linha, "status": "falhou", "erro": "rejeitada"}

        monkeypatch.setattr(service, "_processar_linha", processar_linha)
        job = _job()

        await service.processar(SessaoFalsa(), job, lote, TENANT)

        assert len(job.relatorio) == 2
        assert job.status == StatusLote.PARCIAL
        assert job.sucesso == 0 and job.falhas == 2

    async def test_ja_existia_conta_como_sucesso(self, monkeypatch) -> None:
        lote = _lote(_linha(1))

        async def processar_linha(sessao, tenant, linha, **kwargs):
            return {"linha": linha.numero_linha, "status": "ja_existia"}

        monkeypatch.setattr(service, "_processar_linha", processar_linha)
        job = _job()

        await service.processar(SessaoFalsa(), job, lote, TENANT)

        assert job.sucesso == 1 and job.status == StatusLote.CONCLUIDO


class TestProcessarLinha:
    async def test_chave_ja_autorizada_nao_reemite(self, monkeypatch) -> None:
        fatura = SimpleNamespace(id=uuid.uuid4(), status=StatusFatura.AUTORIZADA)
        sessao = SessaoFalsa(existente=fatura)
        chamou: list = []

        async def emitir(*a, **k):
            chamou.append(True)

        emissao = SimpleNamespace(emitir=emitir)

        desfecho = await service._processar_linha(
            sessao, TENANT, _linha(1), emissao_service=emissao, adapter=None
        )

        assert desfecho["status"] == "ja_existia"
        assert desfecho["invoice_id"] == str(fatura.id)
        assert not chamou, "nota já autorizada não pode ser emitida de novo"

    async def test_fatura_nova_e_autorizada(self, monkeypatch) -> None:
        sessao = SessaoFalsa(existente=None)
        documento = SimpleNamespace(chave="5200258" + "0" * 37)

        async def emitir(sessao_, tenant_, invoice, **kwargs):
            return documento

        emissao = SimpleNamespace(emitir=emitir)

        desfecho = await service._processar_linha(
            sessao, TENANT, _linha(1), emissao_service=emissao, adapter=None
        )

        assert desfecho["status"] == "autorizado"
        assert desfecho["chave"] == documento.chave
        assert sessao.adicionados, "fatura nova precisa ser adicionada à sessão"

    async def test_erro_na_linha_faz_rollback_e_registra(self) -> None:
        sessao = SessaoFalsa(existente=None)

        async def emitir(*a, **k):
            raise RuntimeError("SEFIN recusou")

        emissao = SimpleNamespace(emitir=emitir)

        desfecho = await service._processar_linha(
            sessao, TENANT, _linha(1), emissao_service=emissao, adapter=None
        )

        assert desfecho["status"] == "falhou"
        assert "SEFIN recusou" in desfecho["erro"]
        assert sessao.rollbacks == 1


class TestConsultas:
    async def test_listar_devolve_lista(self) -> None:
        assert await service.listar(SessaoFalsa(), TENANT.id) == []

    async def test_por_id_ausente_levanta(self) -> None:
        with pytest.raises(service.ErroDeLote):
            await service.por_id(SessaoFalsa(), TENANT.id, uuid.uuid4())

    async def test_por_id_existente_devolve(self) -> None:
        job = _job()
        sessao = SessaoFalsa(existente=job)

        assert await service.por_id(sessao, TENANT.id, job.id) is job
