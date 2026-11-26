"""Persistência e consulta do laudo de cálculo tributário.

Fatia 3 da Etapa C. Toda consulta filtra por `tenant_id` **derivado da credencial**,
nunca do corpo — é a regra 6 e o que impede IDOR entre tenants.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tax import CalculoAudit
from app.tax.auditoria import LaudoCalculo


async def registrar(
    sessao: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    laudo: LaudoCalculo,
    invoice_id: uuid.UUID | None = None,
) -> CalculoAudit:
    """Persiste o laudo. Não faz commit: quem chama controla a transação.

    Isso importa: o laudo deve ser gravado **na mesma transação** do documento. Se
    fosse commitado à parte e a emissão falhasse depois, teríamos laudo de um
    cálculo que não virou nota — prova de algo que nunca existiu.
    """
    registro = CalculoAudit(
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        trace_id=laudo.trace_id,
        versao_formato=laudo.versao_formato,
        hash_entrada=laudo.hash_entrada,
        hash_saida=laudo.hash_saida,
        hash_laudo=laudo.hash_laudo,
        data_emissao=laudo.data_emissao,
        regras=list(laudo.regras),
        tabelas=[t.para_dict() for t in laudo.tabelas],
        entrada=laudo.para_dict()["entrada"],
        saida=laudo.para_dict()["saida"],
    )
    sessao.add(registro)
    await sessao.flush()
    return registro


async def por_trace(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, trace_id: str
) -> Sequence[CalculoAudit]:
    """Todos os cálculos de um `trace_id`, sempre restritos ao tenant.

    Devolve lista, não um registro: o mesmo `trace_id` pode cobrir mais de um
    cálculo (produto e serviço na mesma operação), e escolher um deles esconderia
    parte do rastro.
    """
    consulta = (
        select(CalculoAudit)
        .where(CalculoAudit.tenant_id == tenant_id, CalculoAudit.trace_id == trace_id)
        .order_by(CalculoAudit.created_at)
    )
    return (await sessao.execute(consulta)).scalars().all()


async def por_id(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, registro_id: uuid.UUID
) -> CalculoAudit | None:
    """Busca por id **dentro do tenant**. Id de outro tenant devolve None, não erro:
    responder 404 já revela que o id existe em outro lugar."""
    consulta = select(CalculoAudit).where(
        CalculoAudit.id == registro_id, CalculoAudit.tenant_id == tenant_id
    )
    return (await sessao.execute(consulta)).scalar_one_or_none()


async def do_documento(
    sessao: AsyncSession, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID
) -> Sequence[CalculoAudit]:
    consulta = (
        select(CalculoAudit)
        .where(
            CalculoAudit.tenant_id == tenant_id,
            CalculoAudit.invoice_id == invoice_id,
        )
        .order_by(CalculoAudit.created_at)
    )
    return (await sessao.execute(consulta)).scalars().all()


async def verificar_integridade(registro: CalculoAudit) -> bool:
    """Recalcula os hashes a partir do que está gravado.

    Serve para detectar edição direta no banco: se alguém alterou `entrada` ou
    `saida` com SQL na mão, o hash recalculado não bate com o armazenado.
    """
    from app.tax.auditoria import hash_de

    return (
        hash_de(registro.entrada) == registro.hash_entrada
        and hash_de(registro.saida) == registro.hash_saida
    )
