"""Emissão de NFS-e: da fatura ao XML autorizado.

Fluxo, em ordem, com as decisões que importam:

1. **Idempotência primeiro.** Se a fatura já tem documento com chave, devolve o
   existente. Reenviar não duplica nota.
2. **Configuração fiscal é pré-requisito.** Sem município, código de tributação e
   classificação do IBS/CBS não há DPS válida — o erro é local e explicado.
3. **Certificado ativo é obrigatório.** Abre em memória só durante a assinatura.
4. **Número da DPS é consumido de forma monotônica**, com incremento no banco,
   para que dois workers não montem a mesma DPS.
5. **Timeout é ambíguo.** Antes de marcar erro, consulta `GET /dps/{id}`: se a
   SEFIN já gerou a nota, o resultado é sucesso, não falha. Sem isso, a
   retentativa duplicaria documento.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.certificates import service as certificados
from app.core.config import Settings, get_settings
from app.db.models.enums import AmbienteFiscal, StatusFatura, TipoDocumento
from app.db.models.invoice import FiscalDocument, Invoice, InvoiceEvent
from app.db.models.tenant import Tenant, TenantFiscalConfig
from app.nfse.adapter import RespostaEmissao, SefinAdapter, SefinNacionalClient
from app.nfse.constants import FUSO_BR
from app.nfse.dps import (
    VER_APLIC_PADRAO,
    DpsInput,
    ErroDps,
    Ibscbs,
    Prestador,
    Tomador,
    Tributacao,
    dps_para_bytes,
    extrair_id,
)
from app.nfse.errors import ErroSefin, TipoErroFiscal
from app.nfse.signer import ErroAssinatura, assinar_dps

logger = logging.getLogger(__name__)

#: Chaves esperadas em `tenant_fiscal_configs.extra` para o grupo IBS/CBS.
#: Ficam em JSONB porque ainda não têm coluna própria; a validação é explícita.
CHAVES_IBSCBS = ("c_nbs", "c_ind_op", "c_class_trib")


class ErroDeEmissao(Exception):
    """Falha de emissão que o chamador precisa conhecer."""


class ConfiguracaoFiscalAusente(ErroDeEmissao):
    """O tenant não configurou o município/ambiente para emitir."""


class CertificadoAusente(ErroDeEmissao):
    """O tenant não tem certificado A1 ativo."""


async def _config_do_tenant(
    sessao: AsyncSession, tenant_id: Any, ambiente: AmbienteFiscal
) -> TenantFiscalConfig:
    resultado = await sessao.execute(
        select(TenantFiscalConfig)
        .where(
            TenantFiscalConfig.tenant_id == tenant_id,
            TenantFiscalConfig.ambiente == ambiente,
        )
        .order_by(TenantFiscalConfig.created_at)
    )
    config = resultado.scalars().first()
    if config is None:
        raise ConfiguracaoFiscalAusente(
            f"nenhuma configuração fiscal para o ambiente {ambiente.value!r}. "
            "Cadastre com PUT /v1/me/config-fiscal antes de emitir."
        )
    return config


async def _notificar_autorizacao(
    sessao: AsyncSession,
    tenant: Tenant,
    invoice: Invoice,
    documento: FiscalDocument,
) -> None:
    """Registra o evento de webhook da nota autorizada.

    Isolado e tolerante a falha de propósito: webhook é notificação, não parte da
    transação fiscal. Se a criação do registro falhar, a nota continua autorizada
    e o erro vai para o log — o inverso seria perder nota porque o cliente tem
    endpoint mal configurado.
    """
    from app.webhooks import service as webhook_service

    try:
        await webhook_service.enfileirar(
            sessao,
            tenant,
            tipo_evento="nfse.autorizada",
            payload={
                "invoice_id": str(invoice.id),
                "chave": documento.chave,
                "valor": str(invoice.valor_servico),
                "competencia": invoice.competencia,
                "idempotency_key": invoice.idempotency_key,
                "tipo_documento": documento.tipo_documento.value,
            },
        )
    except Exception as exc:
        logger.warning(
            "webhook_nao_enfileirado",
            extra={"invoice_id": str(invoice.id), "erro": str(exc)[:200]},
        )


async def _reservar_numero_dps_no_banco(sessao: AsyncSession, config: TenantFiscalConfig) -> int:
    """Incrementa o contador de DPS atomicamente e devolve o número reservado.

    Dois workers concorrentes recebem números distintos porque o incremento
    acontece no banco, em uma única instrução.
    """
    resultado = await sessao.execute(
        update(TenantFiscalConfig)
        .where(TenantFiscalConfig.id == config.id)
        .values(proximo_numero_dps=TenantFiscalConfig.proximo_numero_dps + 1)
        .returning(TenantFiscalConfig.proximo_numero_dps)
    )
    novo = resultado.scalar_one()
    await sessao.refresh(config)
    return int(novo) - 1


def _ibscbs_da_config(config: TenantFiscalConfig) -> Ibscbs | None:
    """Monta o grupo IBS/CBS a partir de `extra`, ou devolve None.

    Se qualquer chave estiver presente, todas passam a ser exigidas: meio grupo
    IBS/CBS é rejeição garantida pela SEFIN, e é melhor falhar aqui com mensagem
    clara do que receber recusa opaca.
    """
    extra = config.extra or {}
    presentes = [chave for chave in CHAVES_IBSCBS if extra.get(chave)]
    if not presentes:
        return None
    faltando = [chave for chave in CHAVES_IBSCBS if not extra.get(chave)]
    if faltando:
        raise ConfiguracaoFiscalAusente(
            "configuração de IBS/CBS incompleta: falta "
            + ", ".join(faltando)
            + " em tenant_fiscal_configs.extra. Informe todos ou nenhum."
        )
    return Ibscbs(
        c_ind_op=str(extra["c_ind_op"]),
        c_class_trib=str(extra["c_class_trib"]),
        c_nbs=str(extra["c_nbs"]),
        ind_final=str(extra.get("ind_final") or "1"),
        tp_oper=str(extra["tp_oper"]) if extra.get("tp_oper") else None,
    )


def _montar_entrada(
    *,
    invoice: Invoice,
    config: TenantFiscalConfig,
    numero_dps: int,
    certificado_cnpj: str | None,
    settings: Settings,
) -> DpsInput:
    """Converte fatura + configuração em `DpsInput`."""
    if not config.codigo_tributacao_nacional:
        raise ConfiguracaoFiscalAusente(
            "configuração fiscal sem código de tributação nacional (cTribNac). "
            "Cadastre em PUT /v1/me/config-fiscal."
        )

    documento_prestador = certificado_cnpj or ""
    if not documento_prestador:
        raise CertificadoAusente(
            "não foi possível determinar o CNPJ do prestador: o certificado não "
            "traz CNPJ e a configuração fiscal não informa. Ajuste um dos dois."
        )

    tomador = None
    if invoice.tomador_documento or invoice.tomador_nome:
        tomador = Tomador(
            nome=invoice.tomador_nome or "Consumidor não identificado",
            documento=invoice.tomador_documento,
            email=invoice.tomador_email,
        )

    # O grupo IBS/CBS declara se o tomador é o destinatário. Sem tomador, é 0.
    ibscbs = _ibscbs_da_config(config)
    if ibscbs is not None:
        ibscbs.ind_dest = "1" if tomador is not None else "0"

    valor = Decimal(invoice.valor_servico)
    desconto = Decimal(invoice.valor_desconto or 0)
    if desconto and desconto >= valor:
        raise ErroDeEmissao(
            "desconto maior ou igual ao valor do serviço: a DPS ficaria com valor não positivo"
        )

    # Regime do Simples: CRT 1/2/4 -> 3 (ME/EPP), MEI -> 2, regime normal -> 1.
    op_simp_nac = "2" if config.optante_mei else ("3" if config.simples_nacional else "1")

    return DpsInput(
        ambiente=config.ambiente,
        c_mun_emissor=config.municipio_ibge,
        serie=int(config.serie_dps or 1),
        n_dps=numero_dps,
        dh_emi=datetime.now(FUSO_BR),
        prestador=Prestador(
            documento=documento_prestador,
            op_simp_nac=op_simp_nac,
            reg_esp_trib=str((config.extra or {}).get("reg_esp_trib") or "0"),
            reg_ap_trib_sn=str((config.extra or {}).get("reg_ap_trib_sn") or "1")
            if op_simp_nac == "3"
            else None,
            inscricao_municipal=config.inscricao_municipal,
        ),
        tomador=tomador,
        c_trib_nac=config.codigo_tributacao_nacional,
        c_trib_mun=str((config.extra or {}).get("c_trib_mun") or "") or None,
        c_loc_prestacao=config.municipio_ibge,
        x_desc_serv=invoice.descricao_servico,
        valor=valor,
        v_desc_incond=desconto or None,
        tributacao=Tributacao(
            trib_issqn="1",
            tp_ret_issqn="1",
            p_aliq=Decimal(config.aliquota_iss) if config.aliquota_iss is not None else None,
        ),
        ibscbs=ibscbs,
        ver_aplic=VER_APLIC_PADRAO,
    )


async def emitir(
    sessao: AsyncSession,
    tenant: Tenant,
    invoice: Invoice,
    *,
    adapter: SefinAdapter | None = None,
    settings: Settings | None = None,
) -> FiscalDocument:
    """Emite a NFS-e da fatura e devolve o documento autorizado.

    Levanta :class:`ErroDeEmissao` para falha local e
    :class:`~app.nfse.errors.ErroSefin` para recusa/falha da SEFIN.
    """
    conf = settings or get_settings()

    # 1) idempotência: documento já autorizado encerra aqui.
    resultado = await sessao.execute(
        select(FiscalDocument).where(
            FiscalDocument.tenant_id == tenant.id,
            FiscalDocument.invoice_id == invoice.id,
            FiscalDocument.chave.is_not(None),
        )
    )
    existente = resultado.scalars().first()
    if existente is not None:
        logger.info(
            "emissao_idempotente",
            extra={"invoice_id": str(invoice.id), "chave": existente.chave},
        )
        return existente

    config = await _config_do_tenant(sessao, tenant.id, invoice.ambiente)

    registro_cert = await certificados.ativo(sessao, tenant.id)
    if registro_cert is None:
        raise CertificadoAusente(
            "nenhum certificado A1 ativo. Envie o .pfx em POST /v1/me/certificados."
        )
    certificado = certificados.abrir_em_memoria(registro_cert, settings=conf)

    numero_dps = await _reservar_numero_dps_no_banco(sessao, config)

    entrada = _montar_entrada(
        invoice=invoice,
        config=config,
        numero_dps=numero_dps,
        certificado_cnpj=certificado.cnpj,
        settings=conf,
    )

    try:
        # dps_para_bytes serializa com a stdlib; o assinador parseia com lxml.
        dps_xml = dps_para_bytes(entrada)
        dps_assinada = assinar_dps(dps_xml, certificado)
    except (ErroDps, ErroAssinatura) as exc:
        await _registrar_evento(sessao, invoice, "erro_local", mensagem=str(exc))
        invoice.status = StatusFatura.ERRO
        invoice.erro = str(exc)
        await sessao.flush()
        raise ErroDeEmissao(str(exc)) from exc

    id_dps = extrair_id(dps_assinada)
    invoice.status = StatusFatura.PROCESSANDO
    await sessao.flush()

    cliente = adapter or SefinNacionalClient(
        config.ambiente,
        certificado,
        base_url=conf.sefin_base_url or None,
        adn_base_url=None,
        permitir_host_nao_oficial=bool(conf.sefin_permitir_host_nao_oficial),
    )
    proprio = adapter is None

    try:
        resposta = cliente.emitir(dps_assinada)
    except ErroSefin as erro:
        # Timeout ambíguo: a nota pode existir. Consultar antes de acusar falha.
        if erro.pode_ter_sido_processada and id_dps:
            resposta = await _tentar_recuperar(cliente, id_dps, erro)
            if resposta is None:
                raise
            logger.warning(
                "emissao_recuperada_apos_timeout",
                extra={"invoice_id": str(invoice.id), "chave": resposta.chave_acesso},
            )
        else:
            await _registrar_falha(sessao, invoice, erro)
            raise
    finally:
        if proprio:
            cliente.fechar()

    documento = await _persistir_autorizacao(
        sessao,
        invoice=invoice,
        resposta=resposta,
        dps_assinada=dps_assinada,
        ambiente=config.ambiente,
    )
    await _notificar_autorizacao(sessao, tenant, invoice, documento)
    return documento


async def _tentar_recuperar(
    cliente: SefinAdapter, id_dps: str, erro_original: ErroSefin
) -> RespostaEmissao | None:
    """Depois de timeout ambíguo, verifica se a SEFIN já gerou a nota."""
    try:
        chave = cliente.consultar_dps(id_dps)
    except ErroSefin:
        return None
    if not chave:
        return None
    try:
        return cliente.consultar_nfse(chave)
    except ErroSefin:
        logger.warning(
            "nota_existe_mas_nao_foi_baixada",
            extra={"chave": chave, "erro_original": erro_original.tipo.value},
        )
        return None


async def _persistir_autorizacao(
    sessao: AsyncSession,
    *,
    invoice: Invoice,
    resposta: RespostaEmissao,
    dps_assinada: bytes,
    ambiente: AmbienteFiscal,
) -> FiscalDocument:
    documento = FiscalDocument(
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        tipo_documento=TipoDocumento.NFSE,
        ambiente=ambiente,
        chave=resposta.chave_acesso,
        xml_assinado=dps_assinada.decode("utf-8", errors="replace"),
        xml_autorizado=resposta.nfse_xml.decode("utf-8", errors="replace"),
        resposta_bruta=resposta.bruto or None,
        emitido_em=datetime.now(UTC),
    )
    sessao.add(documento)

    invoice.status = StatusFatura.AUTORIZADA
    invoice.processada_em = datetime.now(UTC)
    invoice.erro = None
    await sessao.flush()

    await _registrar_evento(
        sessao,
        invoice,
        "autorizada",
        status="autorizado",
        mensagem=f"chave {resposta.chave_acesso}",
        resposta={
            "chave": resposta.chave_acesso,
            "alertas": [a.as_dict() for a in resposta.alertas],
        },
        fiscal_document_id=documento.id,
    )
    return documento


async def _registrar_falha(sessao: AsyncSession, invoice: Invoice, erro: ErroSefin) -> None:
    invoice.status = (
        StatusFatura.REJEITADA if erro.tipo is TipoErroFiscal.REJEICAO else StatusFatura.ERRO
    )
    invoice.erro = str(erro)
    await sessao.flush()
    await _registrar_evento(
        sessao,
        invoice,
        "rejeitada" if erro.tipo is TipoErroFiscal.REJEICAO else "erro_sefin",
        status=erro.tipo.value,
        mensagem=str(erro),
        resposta=erro.as_dict(),
    )


async def _registrar_evento(
    sessao: AsyncSession,
    invoice: Invoice,
    tipo: str,
    *,
    status: str | None = None,
    mensagem: str | None = None,
    resposta: dict[str, Any] | None = None,
    fiscal_document_id: Any = None,
) -> None:
    sessao.add(
        InvoiceEvent(
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.id,
            fiscal_document_id=fiscal_document_id,
            tipo=tipo,
            status=status,
            mensagem=mensagem,
            resposta=resposta,
        )
    )
    await sessao.flush()
