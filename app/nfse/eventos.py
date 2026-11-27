"""Registro genérico de eventos da NFS-e, usando o catálogo do XSD.

Por que uma rota genérica além da rota de cancelamento: o leiaute tem 16 tipos e
criar 15 rotas quase idênticas só multiplicaria superfície. Aqui o tipo vem do
catálogo, com os campos que o schema exige.

**Cancelamento (101101) é exceção deliberada**: ele muda o status da nota e tem
regra própria de motivo. Manter dois caminhos para a mesma operação permitiria que
um deles esquecesse a mudança de status — o tipo é recusado aqui e aponta para a
rota dedicada.

Regras aplicadas a todos os tipos:

- **Só documento autorizado recebe evento.** Evento para chave inexistente é
  recusado pela SEFIN com código genérico, pior de diagnosticar.
- **O autor é o CNPJ do certificado ativo**, não o do cadastro: quem assina
  responde pelo pedido.
- **O evento é registrado como trilha**, com o XML que a SEFIN devolveu, para
  conferência posterior.

O que este módulo **não** decide: se o tipo é cabível no caso concreto, e se o autor
tem permissão para aquele tipo (prestador só manifesta o que lhe cabe, por exemplo).
O schema não expressa essas regras.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.certificates import service as certificados
from app.core.config import Settings, get_settings
from app.db.models.invoice import FiscalDocument, Invoice, InvoiceEvent
from app.db.models.tenant import Tenant
from app.nfse.adapter import RespostaEvento, SefinAdapter
from app.nfse.documento_autorizado import DocumentoAutorizado
from app.nfse.errors import ErroSefin
from app.nfse.evento import assinar_pedido_evento
from app.nfse.eventos_tipos import (
    TIPOS_DO_CONTRIBUINTE,
    ErroDeEventoCatalogo,
    construir_evento,
    obter_tipo,
)

logger = logging.getLogger(__name__)

#: Tipo com rota dedicada: muda status e tem validação de motivo própria.
CANCELAMENTO = "101101"


class ErroDeEvento(Exception):
    """Evento não pode ser registrado."""


class TipoReservado(ErroDeEvento):
    """O tipo tem caminho próprio e não deve passar por aqui."""


class EventoNaoAplicavel(ErroDeEvento):
    """Tipo de evento que o contribuinte não opera."""


async def _documento_autorizado(
    sessao: AsyncSession, tenant_id: Any, invoice: Invoice
) -> DocumentoAutorizado:
    resultado = await sessao.execute(
        select(FiscalDocument).where(
            FiscalDocument.tenant_id == tenant_id,
            FiscalDocument.invoice_id == invoice.id,
            FiscalDocument.chave.is_not(None),
        )
    )
    documento = resultado.scalars().first()
    if documento is None or not documento.chave:
        raise ErroDeEvento(
            "a fatura não tem documento autorizado com chave; não há nota para receber evento"
        )
    return DocumentoAutorizado(documento=documento, chave=documento.chave)


def validar_tipo(codigo: str, *, permitir_oficio: bool = False) -> None:
    """Recusa cancelamento e, por padrão, os tipos de ofício."""
    if codigo == CANCELAMENTO:
        raise TipoReservado(
            "cancelamento tem rota própria (POST /v1/emissoes/{id}/cancelamento): "
            "ele muda o status da nota e valida o motivo. Usar a rota dedicada."
        )
    tipo = obter_tipo(codigo)  # levanta se não existir
    if not permitir_oficio and codigo not in TIPOS_DO_CONTRIBUINTE:
        raise EventoNaoAplicavel(
            f"o evento {codigo} ({tipo.grupo}) é de ofício — quem o dispara é o fisco, "
            "não o contribuinte. Tipos operáveis: " + ", ".join(TIPOS_DO_CONTRIBUINTE)
        )


async def registrar(
    sessao: AsyncSession,
    tenant: Tenant,
    invoice: Invoice,
    *,
    codigo: str,
    campos: dict[str, str],
    adapter: SefinAdapter | None = None,
    settings: Settings | None = None,
    permitir_oficio: bool = False,
) -> RespostaEvento:
    """Registra um evento do catálogo na NFS-e da fatura."""
    conf = settings or get_settings()
    validar_tipo(codigo, permitir_oficio=permitir_oficio)

    alvo = await _documento_autorizado(sessao, tenant.id, invoice)
    documento, chave = alvo.documento, alvo.chave

    registro_cert = await certificados.ativo(sessao, tenant.id)
    if registro_cert is None:
        raise ErroDeEvento(
            "nenhum certificado A1 ativo: o pedido de evento precisa ser assinado "
            "por quem responde pela nota"
        )
    certificado = certificados.abrir_em_memoria(registro_cert, settings=conf)
    if not certificado.cnpj:
        raise ErroDeEvento(
            "o certificado A1 ativo não identifica CNPJ no titular; "
            "o pedido de evento precisa de autor"
        )

    try:
        pedido_xml = construir_evento(
            codigo,
            chave=chave,
            cnpj_autor=certificado.cnpj,
            campos=campos,
            ambiente="1" if documento.ambiente.value == "producao" else "2",
            dh_evento=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        )
        assinado = assinar_pedido_evento(pedido_xml, certificado)
    except ErroDeEventoCatalogo:
        # Erro de payload (campo ausente, valor fora do enum, motivo curto) é
        # problema da REQUISIÇÃO, não do estado da nota: sobe como está para a
        # borda HTTP responder 422. Engolir aqui virava 409, que sugeriria conflito
        # de estado e faria o cliente tentar de novo a mesma coisa.
        raise

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
        resposta = cliente.registrar_evento(chave, assinado, operacao=f"evento {codigo}")
    except ErroSefin as erro:
        await _registrar_falha(sessao, tenant, invoice, documento, codigo, erro)
        raise
    finally:
        if adapter is None:
            cliente.fechar()

    proxima_sequencia = await _proxima_sequencia(sessao, invoice, codigo)
    sessao.add(
        InvoiceEvent(
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            fiscal_document_id=documento.id,
            tipo=f"evento_{codigo}",
            sequencia=proxima_sequencia,
            status="registrado",
            mensagem=f"evento {codigo} registrado",
            xml_evento=resposta.evento_xml.decode("utf-8", errors="replace")[:20000],
            requisicao={
                "codigo": codigo,
                "campos": campos,
                "chave": chave,
                "cnpj_autor": certificado.cnpj,
                "id_pedido": f"PRE{chave}{codigo}",
            },
            resposta={"data_processamento": resposta.data_processamento},
        )
    )
    await sessao.flush()
    logger.info(
        "nfse_evento_registrado",
        extra={"invoice_id": str(invoice.id), "codigo": codigo},
    )
    return resposta


async def _proxima_sequencia(sessao: AsyncSession, invoice: Invoice, codigo: str) -> int:
    """Sequência do evento para aquele tipo, começando em 1.

    O leiaute admite mais de um evento do mesmo tipo por nota; guardar a sequência
    evita sobrescrever histórico na trilha.
    """
    resultado = await sessao.execute(
        select(func.coalesce(func.max(InvoiceEvent.sequencia), 0)).where(
            InvoiceEvent.invoice_id == invoice.id,
            InvoiceEvent.tipo == f"evento_{codigo}",
        )
    )
    return int(resultado.scalar_one()) + 1


async def _registrar_falha(
    sessao: AsyncSession,
    tenant: Tenant,
    invoice: Invoice,
    documento: FiscalDocument,
    codigo: str,
    erro: ErroSefin,
) -> None:
    sessao.add(
        InvoiceEvent(
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            fiscal_document_id=documento.id,
            tipo=f"evento_{codigo}_falhou",
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


def tipos_disponiveis(*, incluir_oficio: bool = False) -> list[str]:
    from app.nfse.eventos_tipos import TIPOS_EVENTO

    if incluir_oficio:
        return sorted(c for c in TIPOS_EVENTO if c != CANCELAMENTO)
    return sorted(c for c in TIPOS_DO_CONTRIBUINTE if c != CANCELAMENTO)
