"""Rotas de emissão de NFS-e.

`POST /v1/emissoes` é síncrono de propósito nesta fase: o parceiro recebe a chave
ou a rejeição na mesma chamada. A Fase 5 acrescenta o caminho assíncrono por fila
para lote; a semântica de idempotência é a mesma e já está implementada.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import tenant_atual
from app.assessment.service import competencia_de
from app.core.config import Settings, get_settings
from app.danfe import ErroRepresentacao
from app.danfe import gerar as gerar_representacao
from app.danfe.nfe import registrar_todas as registrar_representacoes
from app.danfse.service import ErroDanfse, gerar_pdf_do_documento
from app.db.models.enums import StatusFatura, TipoDocumento
from app.db.models.invoice import FiscalDocument, Invoice
from app.db.models.tenant import Tenant
from app.db.session import get_session
from app.nfse import cancelamento as cancelamento_service
from app.nfse import eventos as eventos_service
from app.nfse import servico as emissao_service
from app.nfse.adapter import SefinMockAdapter
from app.nfse.errors import ErroSefin
from app.nfse.evento import MOTIVOS_CANCELAMENTO
from app.nfse.eventos_tipos import TIPOS_DO_CONTRIBUINTE, TIPOS_EVENTO, ErroDeEventoCatalogo
from app.nfse.injecao import (
    OPERACAO_CANCELAMENTO,
    OPERACAO_EVENTO,
    UF_NACIONAL,
    emitir_com_circuito,
    executar_com_circuito,
)
from app.nfse.resiliencia import registro_padrao
from app.nfse.schemas import DocumentoOut, EmissaoDetalheOut, EmissaoIn, EmissaoOut
from app.nfse.servico import (
    CertificadoAusente,
    ConfiguracaoFiscalAusente,
    ErroDeEmissao,
)
from app.tax import auditoria_service, integracao_emissao

HTTP_409 = 409
HTTP_422 = 422
HTTP_502 = 502

router = APIRouter(tags=["emissao"])
registrar_representacoes()


def _documento_out(documento: FiscalDocument | None) -> DocumentoOut | None:
    if documento is None:
        return None
    return DocumentoOut(
        id=documento.id,
        tipo_documento=documento.tipo_documento.value,
        ambiente=documento.ambiente.value,
        chave=documento.chave,
        emitido_em=documento.emitido_em,
        tem_xml_autorizado=bool(documento.xml_autorizado),
    )


def _emissao_out(
    invoice: Invoice, documento: FiscalDocument | None, *, ja_existia: bool
) -> EmissaoOut:
    return EmissaoOut(
        invoice_id=invoice.id,
        status=invoice.status,
        valor=invoice.valor_servico,
        idempotency_key=invoice.idempotency_key,
        documento=_documento_out(documento),
        chave=documento.chave if documento else None,
        erro=invoice.erro,
        ja_existia=ja_existia,
    )


def _trava_de_idempotencia(tenant_id: uuid.UUID, chave: str) -> int:
    """Identificador de 64 bits (com sinal) para `pg_advisory_xact_lock`.

    Derivado de (tenant, chave) por SHA-256: duas chaves diferentes caem em travas diferentes, e
    o mesmo par sempre cai na mesma. Colisão é teoricamente possível e apenas serializa dois
    pedidos distintos — não corrompe nada.
    """
    resumo = hashlib.sha256(f"{tenant_id}:{chave}".encode()).digest()[:8]
    return int.from_bytes(resumo, "big", signed=True)


def _recusar_payload_divergente(existente: Invoice, dados: BaseModel) -> None:
    """Mesma `Idempotency-Key` com corpo diferente é **409**, não 200 silencioso.

    Reutilizar a chave com outro pedido e receber de volta a nota anterior é o pior desfecho
    possível: o cliente acha que emitiu R$ 100 e o documento que existe é de R$ 50 — e num
    documento fiscal isso é divergência de escrituração, não bug cosmético.

    A comparação usa o `payload` que a própria fatura guardou na criação (`model_dump(mode="json")`),
    então não precisa de coluna nova nem de migração. Corpo idêntico continua devolvendo **200** com
    `ja_existia: true`, que é o comportamento que o cliente que repete espera.
    """
    original = existente.payload or {}
    atual = dados.model_dump(mode="json")
    if original == atual:
        return
    raise HTTPException(
        status_code=HTTP_409,
        detail=(
            "esta `Idempotency-Key` já foi usada com um corpo diferente. "
            "Reenvio idêntico devolve a emissão original; para um documento novo, use outra chave."
        ),
    )


async def _buscar_por_idempotencia(
    db: AsyncSession, tenant_id: uuid.UUID, chave: str
) -> Invoice | None:
    resultado = await db.execute(
        select(Invoice).where(Invoice.tenant_id == tenant_id, Invoice.idempotency_key == chave)
    )
    return resultado.scalar_one_or_none()


async def _documento_da_fatura(db: AsyncSession, invoice: Invoice) -> FiscalDocument | None:
    resultado = await db.execute(
        select(FiscalDocument)
        .where(
            FiscalDocument.tenant_id == invoice.tenant_id, FiscalDocument.invoice_id == invoice.id
        )
        .order_by(FiscalDocument.created_at.desc())
    )
    return resultado.scalars().first()


@router.post(
    "/emissoes",
    response_model=EmissaoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Emite a NFS-e de um serviço (idempotente por idempotency_key)",
    responses={
        200: {"description": "A idempotency_key já havia sido processada"},
        422: {"description": "Configuração fiscal ou certificado ausente"},
        502: {"description": "A SEFIN recusou ou está indisponível"},
    },
)
async def emitir(
    dados: EmissaoIn,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description="Chave idempotente por tenant. Precede o campo do body.",
    ),
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> EmissaoOut:
    """Emite a NFS-e de forma idempotente.

    A chave aceita dois lugares por compatibilidade: o header `Idempotency-Key`
    (contrato novo, recomendado) e o campo `idempotency_key` do body (clientes
    existentes). Se os dois vierem e divergirem, **o header vence** — header é o
    contrato explícito, e escolher o body permitiria que um cliente com proxy que
    injeta header mudasse a chave sem perceber. Se nenhum vier, 422: sem chave não
    há como garantir que um reenvio não duplique a nota.
    """
    chave = idempotency_key or dados.idempotency_key
    if not chave:
        raise HTTPException(
            status_code=HTTP_422,
            detail=(
                "informe a chave de idempotência no header `Idempotency-Key` "
                "(recomendado) ou no campo `idempotency_key` do body"
            ),
        )
    if len(chave) < 8 or len(chave) > 128:
        raise HTTPException(
            status_code=HTTP_422,
            detail="a chave de idempotência deve ter de 8 a 128 caracteres",
        )

    # Serializa o par (tenant, chave) DENTRO da transação, antes de olhar se a fatura existe.
    #
    # Sem isto, duas requisições simultâneas com a mesma `Idempotency-Key` passam as duas pela
    # checagem (nenhuma vê a outra ainda), as duas tentam inserir, e a segunda bate na constraint
    # `uq_invoices_tenant_idempotency_key`. O tratamento de `IntegrityError` existe, mas o erro
    # chega embrulhado pelo driver e a recuperação estourava com `MissingGreenlet` — o cliente
    # recebia 500 num caminho que deveria ser 200 (auditoria §55). Segurar o par antes da leitura
    # evita a corrida em vez de remendar o estrago.
    #
    # `pg_advisory_xact_lock` é liberado no commit/rollback e o escopo é a chave, não a tabela:
    # duas emissões de tenants diferentes (ou de chaves diferentes) seguem em paralelo.
    await db.execute(
        text("select pg_advisory_xact_lock(:chave)"),
        {"chave": _trava_de_idempotencia(tenant.id, chave)},
    )

    existente = await _buscar_por_idempotencia(db, tenant.id, chave)
    if existente is not None:
        _recusar_payload_divergente(existente, dados)
        documento = await _documento_da_fatura(db, existente)
        if existente.status is StatusFatura.AUTORIZADA and documento is not None:
            corpo = _emissao_out(existente, documento, ja_existia=True)
            return JSONResponse(  # type: ignore[return-value]
                status_code=200, content=corpo.model_dump(mode="json")
            )
        # Fatura existe mas não está autorizada: reprocessar seria duplicar
        # tentativa sem o parceiro saber. Devolve o estado atual.
        return _emissao_out(existente, documento, ja_existia=True)

    invoice = Invoice(
        tenant_id=tenant.id,
        idempotency_key=chave,
        status=StatusFatura.PENDENTE,
        tipo_documento=TipoDocumento.NFSE,
        origem=dados.origem,
        ambiente=dados.ambiente,
        valor_servico=dados.valor,
        descricao_servico=dados.descricao,
        # Sem competência explícita, usa o mês corrente: apuração consolida
        # por competência e fatura sem essa informação ficaria fora da apuração.
        competencia=dados.competencia or competencia_de(),
        tomador_documento=dados.tomador_documento,
        tomador_nome=dados.tomador_nome,
        tomador_email=str(dados.tomador_email) if dados.tomador_email else None,
        referencia_externa=dados.referencia_externa,
        payload=dados.model_dump(mode="json"),
    )
    db.add(invoice)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existente = await _buscar_por_idempotencia(db, tenant.id, chave)
        if existente is None:
            raise HTTPException(
                status_code=HTTP_409, detail="conflito de idempotência ao criar a fatura"
            ) from None
        return _emissao_out(existente, await _documento_da_fatura(db, existente), ja_existia=True)

    # Laudo do cálculo na MESMA transação da fatura. Commitado à parte, uma emissão
    # que falhasse depois deixaria laudo de um cálculo que nunca virou nota — prova
    # de algo que não existiu. `getattr` porque o laudo não pode depender de campo
    # opcional do schema: campo ausente vira None, não AttributeError.
    laudo = integracao_emissao.da_emissao(
        emitente={"uf": getattr(dados, "uf", None)},
        tomador=({"documento": dados.tomador_documento} if dados.tomador_documento else None),
        servico={
            "valor": dados.valor,
            "municipio_ibge": getattr(dados, "municipio_ibge", None),
            "codigo_tributacao_nacional": getattr(dados, "codigo_tributacao_nacional", None),
        },
        resultado={},
        data_emissao=date.today(),
        trace_id=invoice.id,
    )
    await auditoria_service.registrar(db, tenant_id=tenant.id, laudo=laudo, invoice_id=invoice.id)

    adaptador = SefinMockAdapter(dados.ambiente) if settings.nfse_adapter == "mock" else None

    try:
        documento = await emitir_com_circuito(
            registro_padrao,
            # Hoje a NFS-e é só padrão nacional: um circuito. Quando houver driver
            # municipal, a chave passa a ser por município e a queda de uma prefeitura
            # não para as outras.
            uf=UF_NACIONAL,
            acao=lambda: emissao_service.emitir(
                db,
                tenant,
                invoice,
                municipio_ibge=dados.municipio_ibge,
                adapter=adaptador,
                settings=settings,
            ),
        )
        await db.commit()
    # `ConfiguracaoFiscalAmbigua` herda de `ErroDeEmissao`: precisa vir ANTES, senão
    # o `except` genérico abaixo a captura e o 422 perde a instrução específica
    # (informar o município). Ordem de `except` é semântica, não estilo.
    except emissao_service.ConfiguracaoFiscalAmbigua as exc:
        await db.rollback()
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc
    # Mesma razão da linha acima: `RotaNaoPermitida` herda de `ErroDeEmissao`, e o genérico
    # descartaria a `pendencia` — que é justamente o que o operador precisa ler (§77).
    except emissao_service.RotaNaoPermitida as exc:
        await db.commit()  # preserva o evento de erro registrado
        detalhe = str(exc)
        if exc.pendencia:
            detalhe = f"{detalhe}. Pendência: {exc.pendencia}"
        raise HTTPException(status_code=HTTP_422, detail=detalhe) from exc
    except (ConfiguracaoFiscalAusente, CertificadoAusente, ErroDeEmissao) as exc:
        await db.commit()  # preserva o evento de erro registrado
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc
    except ErroSefin as exc:
        await db.commit()  # preserva status e evento de rejeição
        raise HTTPException(status_code=HTTP_502, detail=exc.as_dict()) from exc

    await db.refresh(invoice)
    await db.refresh(documento)
    return _emissao_out(invoice, documento, ja_existia=False)


@router.get(
    "/emissoes/{invoice_id}",
    response_model=EmissaoDetalheOut,
    summary="Consulta uma emissão, com o XML autorizado",
)
async def consultar_emissao(
    invoice_id: uuid.UUID,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> EmissaoDetalheOut:
    resultado = await db.execute(
        select(Invoice).where(Invoice.tenant_id == tenant.id, Invoice.id == invoice_id)
    )
    invoice = resultado.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=404, detail="emissão não encontrada")

    documento = await _documento_da_fatura(db, invoice)
    base = _emissao_out(invoice, documento, ja_existia=False)
    return EmissaoDetalheOut(
        **base.model_dump(),
        xml_autorizado=documento.xml_autorizado if documento else None,
    )


@router.get(
    "/emissoes",
    response_model=list[EmissaoOut],
    summary="Lista as emissões do tenant",
)
async def listar_emissoes(
    limite: int = Query(default=50, ge=1, le=200),
    deslocamento: int = Query(default=0, ge=0),
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> list[EmissaoOut]:
    resultado = await db.execute(
        select(Invoice)
        .where(Invoice.tenant_id == tenant.id)
        .order_by(Invoice.created_at.desc())
        .limit(limite)
        .offset(deslocamento)
    )
    saida: list[EmissaoOut] = []
    for invoice in resultado.scalars().all():
        saida.append(
            _emissao_out(invoice, await _documento_da_fatura(db, invoice), ja_existia=False)
        )
    return saida


@router.get(
    "/emissoes/{invoice_id}/danfse",
    summary="Gera o DANFSe (PDF) localmente a partir do XML autorizado",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "PDF do DANFSe"},
        404: {"description": "Emissão não encontrada"},
        422: {"description": "Emissão sem XML autorizado"},
    },
)
async def baixar_danfse(
    invoice_id: uuid.UUID,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> Response:
    resultado = await db.execute(
        select(Invoice).where(Invoice.tenant_id == tenant.id, Invoice.id == invoice_id)
    )
    invoice = resultado.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=404, detail="emissão não encontrada")

    documento = await _documento_da_fatura(db, invoice)
    if documento is None:
        raise HTTPException(status_code=HTTP_422, detail="emissão sem documento fiscal")

    try:
        pdf = gerar_pdf_do_documento(documento)
    except ErroDanfse as exc:
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc

    nome = f"danfse-{documento.chave or invoice.id}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nome}"'},
    )


@router.get(
    "/emissoes/{invoice_id}/representacao",
    summary="Representação impressa do documento (DANFE simplificado, DANFSe)",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "PDF da representação"},
        404: {"description": "Emissão não encontrada"},
        422: {"description": "Representação não existe para este documento"},
    },
)
async def baixar_representacao(
    invoice_id: uuid.UUID,
    formato: str = Query(
        default="danfe_simplificado",
        description="danfe_simplificado (NF-e) ou danfse (NFS-e)",
    ),
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """Escolhe a representação pelo tipo do documento.

    Pedir representação inexistente devolve 422 com a lista do que existe — nunca
    um PDF incompleto, que pareceria válido.
    """
    resultado = await db.execute(
        select(Invoice).where(Invoice.tenant_id == tenant.id, Invoice.id == invoice_id)
    )
    invoice = resultado.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=404, detail="emissão não encontrada")

    documento = await _documento_da_fatura(db, invoice)
    if documento is None or not documento.xml_autorizado:
        raise HTTPException(
            status_code=HTTP_422, detail="emissão sem XML autorizado para representar"
        )

    try:
        pdf = gerar_representacao(
            documento.tipo_documento.value,
            documento.xml_autorizado.encode("utf-8"),
            formato=formato,
        )
    except ErroRepresentacao as exc:
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc

    nome = f"{formato}-{documento.chave or invoice.id}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nome}"'},
    )


class CancelamentoIn(BaseModel):
    """Pedido de cancelamento da NFS-e."""

    c_motivo: str = Field(
        ...,
        description="Código do motivo: 1, 2 ou 9 (conforme o leiaute)",
        examples=["1"],
    )
    x_motivo: str = Field(
        ...,
        min_length=15,
        max_length=255,
        description="Descrição do motivo (15 a 255 caracteres, exigido pelo schema)",
    )


class CancelamentoOut(BaseModel):
    invoice_id: uuid.UUID
    status: str
    chave: str
    data_processamento: str | None = None
    motivos: dict[str, str] = Field(default_factory=dict)


@router.get(
    "/emissoes/cancelamento/motivos",
    summary="Motivos de cancelamento aceitos pelo leiaute",
)
async def motivos_de_cancelamento() -> dict[str, str]:
    return MOTIVOS_CANCELAMENTO


@router.post(
    "/emissoes/{invoice_id}/cancelamento",
    response_model=CancelamentoOut,
    summary="Cancela a NFS-e autorizada",
    responses={
        404: {"description": "Emissão não encontrada"},
        409: {"description": "Emissão não está autorizada ou já está cancelada"},
        422: {"description": "Motivo inválido"},
    },
)
async def cancelar_emissao(
    invoice_id: uuid.UUID,
    dados: CancelamentoIn,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CancelamentoOut:
    """Cancela emitindo evento assinado.

    Só documento autorizado pode ser cancelado, e o autor do evento é o CNPJ do
    certificado ativo — quem assina responde pelo pedido.
    """
    resultado = await db.execute(
        select(Invoice).where(Invoice.tenant_id == tenant.id, Invoice.id == invoice_id)
    )
    invoice = resultado.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=404, detail="emissão não encontrada")

    adaptador = SefinMockAdapter(invoice.ambiente) if settings.nfse_adapter == "mock" else None

    try:
        resposta = await executar_com_circuito(
            registro_padrao,
            uf=UF_NACIONAL,
            operacao=OPERACAO_CANCELAMENTO,
            acao=lambda: cancelamento_service.cancelar(
                db,
                tenant,
                invoice,
                c_motivo=dados.c_motivo,
                x_motivo=dados.x_motivo,
                adapter=adaptador,
                settings=settings,
            ),
        )
        await db.commit()
    except cancelamento_service.DocumentoNaoAutorizado as exc:
        await db.rollback()
        raise HTTPException(status_code=HTTP_409, detail=str(exc)) from exc
    except cancelamento_service.MotivoInvalido as exc:
        await db.rollback()
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc
    except cancelamento_service.ErroDeCancelamento as exc:
        await db.rollback()
        raise HTTPException(status_code=HTTP_409, detail=str(exc)) from exc
    except ErroSefin as exc:
        await db.commit()
        raise HTTPException(status_code=502, detail=exc.as_dict()) from exc

    documento = await _documento_da_fatura(db, invoice)
    await db.refresh(invoice)
    return CancelamentoOut(
        invoice_id=invoice.id,
        status=invoice.status.value,
        chave=documento.chave if documento else "",
        data_processamento=resposta.data_processamento,
        motivos=MOTIVOS_CANCELAMENTO,
    )


@router.get(
    "/emissoes/eventos/tipos",
    summary="Catálogo dos 16 tipos de evento da NFS-e (do XSD oficial)",
)
async def tipos_de_evento() -> list[dict[str, object]]:
    """Estrutura de cada tipo de evento, com os campos que o schema exige.

    A descrição fixa (`xDesc`) é do leiaute, não sugestão: quem monta evento com
    texto próprio tem o pedido recusado. Aqui ela vem pronta.
    """
    from app.nfse.eventos_tipos import X_DESC

    return [
        {
            "codigo": tipo.codigo,
            "grupo": tipo.grupo,
            "descricao": X_DESC[tipo.codigo],
            "operavel_pelo_contribuinte": tipo.codigo in TIPOS_DO_CONTRIBUINTE,
            "campos": [
                {"nome": c.nome, "tipo": c.tipo, "obrigatorio": c.obrigatorio} for c in tipo.campos
            ],
        }
        for tipo in sorted(TIPOS_EVENTO.values(), key=lambda t: t.codigo)
    ]


class EventoIn(BaseModel):
    """Registro de evento do catálogo do leiaute."""

    codigo: str = Field(
        ...,
        description="Código do tipo (6 dígitos). Cancelamento (101101) tem rota própria.",
        examples=["202201"],
    )
    campos: dict[str, str] = Field(
        default_factory=dict,
        description="Campos exigidos pelo tipo. `xDesc` é gerado pelo catálogo.",
    )


class EventoRegistradoOut(BaseModel):
    invoice_id: uuid.UUID
    codigo: str
    status: str
    data_processamento: str | None = None


@router.get(
    "/emissoes/eventos/disponiveis",
    summary="Tipos de evento que o contribuinte pode registrar",
)
async def eventos_disponiveis(
    incluir_oficio: bool = Query(default=False),
) -> dict[str, object]:
    return {
        "tipos": eventos_service.tipos_disponiveis(incluir_oficio=incluir_oficio),
        "observacao": (
            "Cancelamento (101101) não aparece: use POST /v1/emissoes/{id}/cancelamento. "
            "Os tipos de ofício só aparecem com incluir_oficio=true e são disparados "
            "pelo fisco, não pelo contribuinte."
        ),
    }


@router.post(
    "/emissoes/{invoice_id}/eventos",
    response_model=EventoRegistradoOut,
    summary="Registra um evento do catálogo na NFS-e",
    responses={
        404: {"description": "Emissão não encontrada"},
        409: {"description": "Emissão sem documento autorizado"},
        422: {"description": "Tipo reservado, de ofício ou campo inválido"},
    },
)
async def registrar_evento(
    invoice_id: uuid.UUID,
    dados: EventoIn,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> EventoRegistradoOut:
    resultado = await db.execute(
        select(Invoice).where(Invoice.tenant_id == tenant.id, Invoice.id == invoice_id)
    )
    invoice = resultado.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=404, detail="emissão não encontrada")

    adaptador = SefinMockAdapter(invoice.ambiente) if settings.nfse_adapter == "mock" else None

    try:
        resposta = await executar_com_circuito(
            registro_padrao,
            uf=UF_NACIONAL,
            operacao=OPERACAO_EVENTO,
            acao=lambda: eventos_service.registrar(
                db,
                tenant,
                invoice,
                codigo=dados.codigo,
                campos=dados.campos,
                adapter=adaptador,
                settings=settings,
            ),
        )
        await db.commit()
    except eventos_service.TipoReservado as exc:
        await db.rollback()
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc
    except eventos_service.EventoNaoAplicavel as exc:
        await db.rollback()
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc
    except ErroDeEventoCatalogo as exc:
        # Tipo fora do catálogo é erro de requisição, não falha do servidor.
        await db.rollback()
        raise HTTPException(status_code=HTTP_422, detail=str(exc)) from exc
    except eventos_service.ErroDeEvento as exc:
        await db.rollback()
        raise HTTPException(status_code=HTTP_409, detail=str(exc)) from exc
    except ErroSefin as exc:
        await db.commit()
        raise HTTPException(status_code=502, detail=exc.as_dict()) from exc

    return EventoRegistradoOut(
        invoice_id=invoice.id,
        codigo=dados.codigo,
        status=invoice.status.value,
        data_processamento=resposta.data_processamento,
    )
