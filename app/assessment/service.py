"""Apuração por tenant e competência, e geração de guia.

Consolida o que foi **efetivamente autorizado** na competência — documento
autorizado é o único que gera obrigação. Nota rejeitada, cancelada ou em erro não
entra na apuração, e isso é verificado no filtro, não presumido.

ISS usa a alíquota configurada no município do tenant; IBS/CBS usa o motor
tributário com a tabela do ano da competência. As duas fontes são declaradas na
resposta para que a conferência seja possível sem abrir o banco.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.providers import (
    DadosApuracao,
    ErroDeGuia,
    Guia,
    obter_provedor,
)
from app.db.models.enums import (
    AmbienteFiscal,
    ProvedorGuia,
    StatusApuracao,
    StatusFatura,
    TipoDocumento,
)
from app.db.models.invoice import FiscalDocument, Invoice
from app.db.models.ops import TaxAssessment
from app.db.models.tenant import TenantFiscalConfig
from app.tax.rtc import BaseCalculoNfse, ErroCalculoTributario, calcular_ibscbs

logger = logging.getLogger(__name__)

FORMATO_COMPETENCIA = 7  # AAAA-MM


class ErroDeApuracao(Exception):
    """Falha de apuração."""


class CompetenciaInvalida(ErroDeApuracao):
    """Competência em formato inválido."""


def validar_competencia(competencia: str) -> str:
    """Valida ``AAAA-MM`` e devolve normalizado."""
    if len(competencia) != FORMATO_COMPETENCIA or competencia[4] != "-":
        raise CompetenciaInvalida(
            f"competência deve ser AAAA-MM (ex.: 2026-11); recebeu {competencia!r}"
        )
    try:
        ano, mes = int(competencia[:4]), int(competencia[5:])
    except ValueError as exc:
        raise CompetenciaInvalida(f"competência inválida: {competencia!r}") from exc
    if not 2000 <= ano <= 2100 or not 1 <= mes <= 12:
        raise CompetenciaInvalida(f"competência fora de faixa: {competencia!r}")
    return competencia


async def _aliquota_iss(
    sessao: AsyncSession, tenant_id: Any, ambiente: AmbienteFiscal
) -> Decimal | None:
    """Alíquota de ISS configurada para o município do tenant."""
    resultado = await sessao.execute(
        select(TenantFiscalConfig)
        .where(
            TenantFiscalConfig.tenant_id == tenant_id,
            TenantFiscalConfig.ambiente == ambiente,
        )
        .order_by(TenantFiscalConfig.created_at)
    )
    config = resultado.scalars().first()
    if config is None or config.aliquota_iss is None:
        return None
    return Decimal(config.aliquota_iss)


async def consolidar(
    sessao: AsyncSession,
    tenant_id: Any,
    competencia: str,
    *,
    provedor: ProvedorGuia = ProvedorGuia.MAN,
    ambiente: AmbienteFiscal = AmbienteFiscal.HOMOLOGACAO,
) -> TaxAssessment:
    """Consolida a competência e grava (ou atualiza) a apuração."""
    competencia = validar_competencia(competencia)
    ano = int(competencia[:4])

    # Só documento AUTORIZADO gera obrigação.
    resultado = await sessao.execute(
        select(Invoice)
        .join(FiscalDocument, FiscalDocument.invoice_id == Invoice.id)
        .where(
            Invoice.tenant_id == tenant_id,
            Invoice.status == StatusFatura.AUTORIZADA,
            FiscalDocument.tipo_documento == TipoDocumento.NFSE,
            Invoice.competencia == competencia,
        )
        .distinct()
    )
    faturas = list(resultado.scalars().all())

    aliquota_iss = await _aliquota_iss(sessao, tenant_id, ambiente)

    total_servicos = Decimal("0.00")
    total_iss = Decimal("0.00")
    total_tributos = Decimal("0.00")
    avisos: list[str] = []
    if aliquota_iss is None and faturas:
        avisos.append("alíquota de ISS não configurada no município: o total de ISS ficou zerado")

    for fatura in faturas:
        valor = Decimal(fatura.valor_servico)
        desconto = Decimal(fatura.valor_desconto or 0)
        base = valor - desconto
        total_servicos += valor

        iss_fatura = (
            (base * aliquota_iss).quantize(Decimal("0.01")) if aliquota_iss else Decimal("0.00")
        )
        total_iss += iss_fatura

        try:
            calculo = calcular_ibscbs(
                BaseCalculoNfse(
                    valor_servico=valor, desconto_incondicional=desconto, iss=iss_fatura
                ),
                ano_fato_gerador=ano,
            )
            total_tributos += calculo.valor_total
        except ErroCalculoTributario as exc:
            avisos.append(f"fatura {fatura.id}: {exc}")

    existente = await sessao.execute(
        select(TaxAssessment).where(
            TaxAssessment.tenant_id == tenant_id,
            TaxAssessment.competencia == competencia,
            TaxAssessment.provedor == provedor,
        )
    )
    apuracao = existente.scalars().first()
    if apuracao is None:
        apuracao = TaxAssessment(tenant_id=tenant_id, competencia=competencia, provedor=provedor)
        sessao.add(apuracao)

    apuracao.total_servicos = total_servicos
    apuracao.total_iss = total_iss
    apuracao.total_tributos = total_tributos
    apuracao.quantidade_documentos = len(faturas)
    apuracao.status = StatusApuracao.FECHADA
    apuracao.erro = None
    apuracao.payload = {
        "avisos": avisos,
        "aliquota_iss": str(aliquota_iss) if aliquota_iss is not None else None,
        "ambiente": ambiente.value,
        "ano_fato_gerador": ano,
        "faturas": [str(f.id) for f in faturas],
    }
    await sessao.flush()
    return apuracao


async def gerar_guia(sessao: AsyncSession, apuracao: TaxAssessment) -> Guia:
    """Gera a guia da apuração com o provedor configurado."""
    dados = DadosApuracao(
        tenant_id=str(apuracao.tenant_id),
        competencia=apuracao.competencia,
        total_servicos=Decimal(apuracao.total_servicos),
        total_iss=Decimal(apuracao.total_iss),
        total_tributos=Decimal(apuracao.total_tributos),
        quantidade_documentos=apuracao.quantidade_documentos,
    )
    provedor = obter_provedor(apuracao.provedor)
    try:
        guia = provedor.gerar(dados)
    except ErroDeGuia as exc:
        apuracao.status = StatusApuracao.FALHOU
        apuracao.erro = str(exc)
        await sessao.flush()
        raise

    apuracao.guia_numero = guia.numero
    apuracao.vencimento = guia.vencimento
    apuracao.linha_digitavel = guia.linha_digitavel
    apuracao.status = StatusApuracao.ABERTA
    apuracao.erro = None
    apuracao.payload = {
        **(apuracao.payload or {}),
        "guia": guia.to_dict(),
        "gerado_em": datetime.now(UTC).isoformat(),
    }
    await sessao.flush()
    return guia


async def listar(
    sessao: AsyncSession, tenant_id: Any, *, limite: int = 50, deslocamento: int = 0
) -> list[TaxAssessment]:
    resultado = await sessao.execute(
        select(TaxAssessment)
        .where(TaxAssessment.tenant_id == tenant_id)
        .order_by(TaxAssessment.competencia.desc())
        .limit(limite)
        .offset(deslocamento)
    )
    return list(resultado.scalars().all())


async def por_id(sessao: AsyncSession, tenant_id: Any, apuracao_id: Any) -> TaxAssessment:
    resultado = await sessao.execute(
        select(TaxAssessment).where(
            TaxAssessment.tenant_id == tenant_id, TaxAssessment.id == apuracao_id
        )
    )
    apuracao = resultado.scalars().first()
    if apuracao is None:
        raise ErroDeApuracao("apuração não encontrada")
    return apuracao


def competencia_de(quando: date | None = None) -> str:
    """Competência ``AAAA-MM`` da data informada (padrão: hoje)."""
    momento = quando or datetime.now(UTC).date()
    return f"{momento.year:04d}-{momento.month:02d}"
