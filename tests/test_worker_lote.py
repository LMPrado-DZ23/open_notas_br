"""`processar_lote` do worker e o entrypoint do healthcheck, provados de verdade.

`processar_lote` concentra as guardas que impedem o worker de processar lote órfão: job inexistente,
tenant inexistente, relatório vazio. Sem teste, um `None` mal tratado viraria `AttributeError` no meio
da madrugada, com o lote preso em PENDENTE.

O healthcheck é executado como **subprocesso** (`python -m app.worker.healthcheck`), que é exatamente
como o Docker o chama. Sem isso, o `if __name__ == "__main__"` nunca é exercitado — e é ele que decide
se o container reinicia.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

from app.worker import main as worker

RAIZ = Path(__file__).resolve().parent.parent


class SessaoFalsa:
    """Sessão mínima: `get(modelo, pk)` devolve o que o teste mandar, por identidade do modelo."""

    def __init__(self, objetos: dict[object, object | None]) -> None:
        self._objetos = objetos
        self.commits = 0

    async def get(self, modelo: object, pk: object) -> object | None:
        return self._objetos.get(modelo)

    async def commit(self) -> None:
        self.commits += 1

    async def __aenter__(self) -> SessaoFalsa:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


def _preparar(monkeypatch, objetos: dict[object, object | None], chamadas: list | None = None):
    """Monta o worker com sessão falsa e modelos sentinela, sem banco."""
    from app.db.models import ops
    from app.db.models import tenant as modelo_tenant

    job_sentinela = type("BatchJobSentinela", (), {})
    tenant_sentinela = type("TenantSentinela", (), {})
    # Chave do dicionário do teste foi criada ANTES do patch: comparar com `ops.BatchJob` depois do
    # patch daria sempre falso e o dublê devolveria `None`.
    batchjob_real = ops.BatchJob
    monkeypatch.setattr(ops, "BatchJob", job_sentinela)
    monkeypatch.setattr(modelo_tenant, "Tenant", tenant_sentinela)
    monkeypatch.setattr("app.nfse.factory.montar_adapter", lambda conf, *a, **k: object())

    remapeado = {
        job_sentinela if chave is batchjob_real else chave: valor
        for chave, valor in objetos.items()
    }
    sessao = SessaoFalsa(remapeado)
    monkeypatch.setattr("app.db.session.obter_sessionmaker_worker", lambda: lambda: sessao)

    if chamadas is not None:

        async def processar_falso(*args, **kwargs):
            chamadas.append((args, kwargs))

        monkeypatch.setattr("app.batches.service.processar", processar_falso)

    return sessao, job_sentinela, tenant_sentinela


class TestProcessarLote:
    async def test_lote_inexistente_nao_explode(self, monkeypatch) -> None:
        sessao, _, _ = _preparar(monkeypatch, {})

        saida = await worker.processar_lote({}, str(uuid.uuid4()))

        assert "não encontrado" in saida
        assert sessao.commits == 0

    async def test_tenant_inexistente_nao_explode(self, monkeypatch) -> None:
        from app.db.models import ops

        job = SimpleNamespace(tenant_id=uuid.uuid4(), relatorio=[], sucesso=0, falhas=0)
        sessao, _, _ = _preparar(monkeypatch, {ops.BatchJob: job})

        saida = await worker.processar_lote({}, str(uuid.uuid4()))

        assert "tenant" in saida and "não encontrado" in saida
        assert sessao.commits == 0

    async def test_lote_valido_processa_e_resume(self, monkeypatch) -> None:
        from app.db.models import ops

        tenant = SimpleNamespace(id=uuid.uuid4())
        job = SimpleNamespace(
            tenant_id=tenant.id,
            relatorio=[{"linha": 1, "idempotency_key": "k1", "erro": None}],
            sucesso=2,
            falhas=1,
        )
        chamadas: list = []
        sessao, _, tenant_sentinela = _preparar(monkeypatch, {ops.BatchJob: job}, chamadas)
        sessao._objetos[tenant_sentinela] = tenant

        saida = await worker.processar_lote({}, str(uuid.uuid4()))

        assert "2 sucesso" in saida and "1 falha" in saida
        assert sessao.commits == 1
        assert chamadas, "o serviço de lote precisa ser chamado"

    async def test_relatorio_vazio_ainda_processa(self, monkeypatch) -> None:
        from app.db.models import ops

        tenant = SimpleNamespace(id=uuid.uuid4())
        job = SimpleNamespace(tenant_id=tenant.id, relatorio=None, sucesso=0, falhas=0)
        chamadas: list = []
        sessao, _, tenant_sentinela = _preparar(monkeypatch, {ops.BatchJob: job}, chamadas)
        sessao._objetos[tenant_sentinela] = tenant

        saida = await worker.processar_lote({}, str(uuid.uuid4()))

        assert "0 sucesso" in saida
        assert chamadas


class TestEntrypointDoHealthcheck:
    def test_comando_do_docker_funciona_sem_redis(self) -> None:
        """`python -m app.worker.healthcheck` precisa sair 1, não estourar traceback."""
        ambiente = {
            **os.environ,
            "REDIS_URL": "redis://127.0.0.1:1/0",
            "PYTHONPATH": str(RAIZ / "src") + os.pathsep + str(RAIZ),
        }

        resultado = subprocess.run(
            [sys.executable, "-m", "app.worker.healthcheck"],
            capture_output=True,
            text=True,
            timeout=90,
            env=ambiente,
            cwd=RAIZ,
        )

        assert resultado.returncode == 1
        assert "redis inacess" in resultado.stderr
