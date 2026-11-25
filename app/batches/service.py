"""Processamento de lote: cada linha vira uma emissão, com relatório por linha.

Regras de produto:

- **Uma linha com problema não para o lote.** O relatório diz qual linha falhou e
  por quê; o resto é processado.
- **Idempotência por linha.** Reprocessar o mesmo lote não duplica nota: a
  `idempotency_key` da linha é a mesma e a emissão devolve "já existia".
- **O relatório é gravado mesmo quando tudo falha.** Lote sem relatório é lote que
  o usuário não consegue auditar.
- O status do lote reflete o conjunto: `CONCLUIDO` com falhas parciais continua
  concluído, mas com contagem explícita de sucesso e falha.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.batches.csv import LinhaLote, LoteLido, ler_csv
from app.db.models.enums import StatusFatura, StatusLote
from app.db.models.invoice import Invoice
from app.db.models.ops import BatchJob
from app.db.models.tenant import Tenant
from app.nfse.adapter import SefinAdapter

logger = logging.getLogger(__name__)


class ErroDeLote(Exception):
    """Falha ao criar ou processar lote."""


def _agora() -> datetime:
    return datetime.now(UTC)


async def criar(
    sessao: AsyncSession,
    tenant: Tenant,
    *,
    nome_arquivo: str,
    conteudo: bytes,
) -> tuple[BatchJob, LoteLido]:
    """Lê o CSV e registra o lote como pendente."""
    lote = ler_csv(conteudo)
    job = BatchJob(
        tenant_id=tenant.id,
        tipo="nfse",
        status=StatusLote.PENDENTE,
        nome_arquivo=nome_arquivo[:255],
        total_linhas=lote.total,
        processadas=0,
        sucesso=0,
        falhas=0,
        relatorio=[
            {
                "linha": linha.numero_linha,
                "status": "ignorada" if not linha.valida else "pendente",
                "erro": linha.erro,
                "idempotency_key": linha.idempotency_key,
            }
            for linha in lote.linhas
        ],
    )
    sessao.add(job)
    await sessao.flush()
    return job, lote


async def processar(
    sessao: AsyncSession,
    job: BatchJob,
    lote: LoteLido,
    tenant: Tenant,
    *,
    adapter: SefinAdapter | None = None,
) -> BatchJob:
    """Processa cada linha válida e grava o relatório final.

    `adapter` é passado explicitamente para que o teste use o dublê sem tocar em
    rede, e para que a escolha de adapter seja decisão do chamador.
    """
    from app.nfse import servico as emissao_service

    job.status = StatusLote.PROCESSANDO
    job.iniciado_em = _agora()
    await sessao.flush()

    relatorio: list[dict[str, Any]] = []
    sucesso = 0
    falhas = 0

    for linha in lote.linhas:
        if not linha.valida:
            relatorio.append(
                {
                    "linha": linha.numero_linha,
                    "status": "ignorada",
                    "erro": linha.erro,
                    "idempotency_key": linha.idempotency_key,
                }
            )
            falhas += 1
            continue

        desfecho = await _processar_linha(
            sessao, tenant, linha, emissao_service=emissao_service, adapter=adapter
        )
        relatorio.append(desfecho)
        if desfecho["status"] in ("autorizado", "ja_existia"):
            sucesso += 1
        else:
            falhas += 1

        job.processadas += 1
        job.sucesso = sucesso
        job.falhas = falhas
        # JSONB não é rastreado por mutação: sem `flag_modified`, o SQLAlchemy pode
        # não marcar a coluna como alterada e o relatório parcial se perde no
        # commit, deixando o lote com o último item apenas.
        job.relatorio = list(relatorio)
        flag_modified(job, "relatorio")
        await sessao.flush()

    job.relatorio = list(relatorio)
    flag_modified(job, "relatorio")
    job.processadas = lote.total
    job.sucesso = sucesso
    job.falhas = falhas
    job.finalizado_em = _agora()
    # `PARCIAL` existe justamente para lote com falha: chamar de CONCLUIDO
    # esconderia que alguma linha não virou nota.
    job.status = StatusLote.CONCLUIDO if falhas == 0 else StatusLote.PARCIAL
    await sessao.flush()
    logger.info(
        "lote_processado",
        extra={
            "job_id": str(job.id),
            "total": job.total_linhas,
            "sucesso": sucesso,
            "falhas": falhas,
        },
    )
    return job


async def _processar_linha(
    sessao: AsyncSession,
    tenant: Tenant,
    linha: LinhaLote,
    *,
    emissao_service: Any,
    adapter: SefinAdapter | None,
) -> dict[str, Any]:
    """Emite uma linha e devolve o registro para o relatório."""
    assert linha.valor is not None  # garantido por LinhaLote.valida
    from app.assessment.service import competencia_de

    try:
        # Reprocessar o lote não pode duplicar nota: se a chave já foi usada, a
        # linha entra no relatório como "já existia" e reaproveita o documento.
        existente = await sessao.execute(
            select(Invoice).where(
                Invoice.tenant_id == tenant.id,
                Invoice.idempotency_key == linha.idempotency_key,
            )
        )
        fatura_anterior = existente.scalars().first()
        if fatura_anterior is not None and fatura_anterior.status == StatusFatura.AUTORIZADA:
            return {
                "linha": linha.numero_linha,
                "status": "ja_existia",
                "invoice_id": str(fatura_anterior.id),
                "chave": None,
                "idempotency_key": linha.idempotency_key,
                "erro": None,
            }

        invoice = fatura_anterior or Invoice(
            tenant_id=tenant.id,
            idempotency_key=linha.idempotency_key,
            status=StatusFatura.PENDENTE,
            valor_servico=str(linha.valor),
            descricao_servico=linha.descricao,
            competencia=linha.competencia or competencia_de(),
            tomador_nome=linha.tomador_nome,
            tomador_documento=linha.tomador_documento,
        )
        if fatura_anterior is None:
            sessao.add(invoice)
            await sessao.flush()

        documento = await emissao_service.emitir(sessao, tenant, invoice, adapter=adapter)
        return {
            "linha": linha.numero_linha,
            "status": "autorizado",
            "invoice_id": str(invoice.id),
            "chave": documento.chave,
            "idempotency_key": linha.idempotency_key,
            "erro": None,
        }
    except Exception as exc:
        await sessao.rollback()
        logger.warning(
            "lote_linha_falhou",
            extra={"linha": linha.numero_linha, "erro": str(exc)[:200]},
        )
        return {
            "linha": linha.numero_linha,
            "status": "falhou",
            "idempotency_key": linha.idempotency_key,
            "erro": str(exc)[:500],
        }


async def listar(
    sessao: AsyncSession, tenant_id: Any, *, limite: int = 50, deslocamento: int = 0
) -> list[BatchJob]:
    resultado = await sessao.execute(
        select(BatchJob)
        .where(BatchJob.tenant_id == tenant_id)
        .order_by(BatchJob.created_at.desc())
        .limit(limite)
        .offset(deslocamento)
    )
    return list(resultado.scalars().all())


async def por_id(sessao: AsyncSession, tenant_id: Any, job_id: Any) -> BatchJob:
    resultado = await sessao.execute(
        select(BatchJob).where(BatchJob.tenant_id == tenant_id, BatchJob.id == job_id)
    )
    job = resultado.scalars().first()
    if job is None:
        raise ErroDeLote("lote não encontrado")
    return job
