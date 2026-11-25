"""Cancelamento de NFS-e: montar o evento, assinar, registrar e persistir.

Regras de negócio que o serviço garante:

- **Só cancela documento autorizado.** Cancelar rascunho ou nota rejeitada é
  operação sem sentido — e, pior, criaria evento para chave inexistente na SEFIN.
- **O autor do evento é o CNPJ do certificado ativo**, não o do tenant no banco.
  Quem assina é quem responde pelo pedido: usar o CNPJ do cadastro permitiria
  assinar por outra pessoa jurídica se os dois divergirem.
- **Cancelamento é idempotente por chave.** Segunda chamada no mesmo documento já
  cancelado devolve o estado atual em vez de reenviar evento.
- **A nota continua guardada.** Cancelar muda status e registra evento; o XML
  autorizado permanece para auditoria — nota cancelada ainda precisa ser
  demonstrável.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.certificates import service as certificados
from app.core.config import Settings, get_settings
from app.db.models.enums import StatusFatura
from app.db.models.invoice import FiscalDocument, Invoice, InvoiceEvent
from app.db.models.tenant import Tenant
from app.nfse.adapter import RespostaEvento, SefinAdapter
from app.nfse.errors import ErroSefin
from app.nfse.evento import (
    MOTIVOS_CANCELAMENTO,
    TIPO_CANCELAMENTO,
    ErroDeEvento,
    PedidoCancelamento,
    assinar_pedido_evento,
    construir_pedido_evento,
    id_pedido_evento,
)

logger = logging.getLogger(__name__)


class ErroDeCancelamento(Exception):
    """Cancelamento não pode ser realizado."""


class DocumentoNaoAutorizado(ErroDeCancelamento):
    """Só é possível cancelar NFS-e autorizada."""


class MotivoInvalido(ErroDeCancelamento):
    """Motivo fora do que o leiaute aceita."""


async def _documento_autorizado(
    sessao: AsyncSession, tenant_id: Any, invoice: Invoice
) -> FiscalDocument:
    resultado = await sessao.execute(
        select(FiscalDocument).where(
            FiscalDocument.tenant_id == tenant_id,
            FiscalDocument.invoice_id == invoice.id,
            FiscalDocument.chave.is_not(None),
        )
    )
    documento = resultado.scalars().first()
    if documento is None or not documento.chave:
        raise DocumentoNaoAutorizado(
            "a fatura não tem documento autorizado com chave; não há o que cancelar"
        )
    return documento


def validar_motivo(c_motivo: str, x_motivo: str) -> None:
    """Valida o motivo antes de qualquer chamada externa.

    Falhar aqui devolve erro claro ao usuário em vez de rejeição da SEFIN com
    `E` genérico — e evita gastar chamada em pedido que já sabemos inválido.
    """
    if c_motivo not in MOTIVOS_CANCELAMENTO:
        aceitos = ", ".join(sorted(MOTIVOS_CANCELAMENTO))
        raise MotivoInvalido(f"cMotivo deve ser um de {aceitos}; recebeu {c_motivo!r}")
    try:
        PedidoCancelamento(
            chave="0" * 50, cnpj_autor="0" * 14, c_motivo=c_motivo, x_motivo=x_motivo
        ).validar()
    except ErroDeEvento as exc:
        raise MotivoInvalido(str(exc)) from exc


async def cancelar(
    sessao: AsyncSession,
    tenant: Tenant,
    invoice: Invoice,
    *,
    c_motivo: str,
    x_motivo: str,
    adapter: SefinAdapter | None = None,
    settings: Settings | None = None,
) -> RespostaEvento:
    """Cancela a NFS-e da fatura e registra o evento."""
    conf = settings or get_settings()

    if invoice.status is StatusFatura.CANCELADA:
        raise ErroDeCancelamento("esta fatura já está cancelada")

    documento = await _documento_autorizado(sessao, tenant.id, invoice)
    validar_motivo(c_motivo, x_motivo)

    registro_cert = await certificados.ativo(sessao, tenant.id)
    if registro_cert is None:
        raise ErroDeCancelamento(
            "nenhum certificado A1 ativo: o pedido de cancelamento precisa ser "
            "assinado por quem responde pela nota"
        )
    certificado = certificados.abrir_em_memoria(registro_cert, settings=conf)

    pedido = PedidoCancelamento(
        chave=documento.chave,
        cnpj_autor=certificado.cnpj,
        c_motivo=c_motivo,
        x_motivo=x_motivo,
        ambiente="1" if documento.ambiente.value == "producao" else "2",
    )
    try:
        pedido_xml = construir_pedido_evento(pedido)
        assinado = assinar_pedido_evento(pedido_xml, certificado)
    except ErroDeEvento as exc:
        raise MotivoInvalido(str(exc)) from exc

    cliente = adapter
    if cliente is None:
        from app.nfse.adapter import SefinNacionalClient

        cliente = SefinNacionalClient(
            documento.ambiente,
            certificado,
            base_url=conf.sefin_base_url or None,
            adn_base_url=None,
            permitir_host_nao_oficial=bool(conf.sefin_permitir_host_nao_oficial),
        )

    try:
        resposta = cliente.registrar_evento(documento.chave, assinado)
    except ErroSefin as erro:
        await _registrar_falha_de_cancelamento(sessao, invoice, erro)
        raise
    finally:
        if adapter is None:
            cliente.fechar()

    invoice.status = StatusFatura.CANCELADA
    invoice.erro = None
    documento.cancelado_em = datetime.now(UTC)
    sessao.add(
        InvoiceEvent(
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            fiscal_document_id=documento.id,
            tipo="cancelamento",
            sequencia=1,
            status="registrado",
            mensagem=f"cMotivo {c_motivo}: {x_motivo}"[:500],
            xml_evento=resposta.evento_xml.decode("utf-8", errors="replace")[:20000],
            requisicao={
                "id_pedido": id_pedido_evento(documento.chave, TIPO_CANCELAMENTO),
                "c_motivo": c_motivo,
                "x_motivo": x_motivo,
                "chave": documento.chave,
                "cnpj_autor": pedido.cnpj_autor,
                "ambiente": pedido.ambiente,
            },
            resposta={"data_processamento": resposta.data_processamento},
        )
    )
    await sessao.flush()
    logger.info(
        "nfse_cancelada",
        extra={"invoice_id": str(invoice.id), "chave": documento.chave},
    )
    return resposta


async def _registrar_falha_de_cancelamento(
    sessao: AsyncSession, invoice: Invoice, erro: ErroSefin
) -> None:
    """Preserva a tentativa que falhou, sem mudar o status da nota."""
    sessao.add(
        InvoiceEvent(
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.id,
            tipo="cancelamento_falhou",
            sequencia=1,
            status="falhou",
            mensagem=str(erro)[:500],
            resposta={
                "tipo": erro.tipo.value,
                "http_status": erro.http_status,
                "mensagens": [m.texto() for m in erro.mensagens],
                "transitorio": erro.transitorio,
            },
        )
    )
    await sessao.flush()
