"""Rotas de tenant.

Duas famílias:

- **Administrativas** (``/v1/tenants``): criação e listagem, protegidas por
  `X-Admin-Token`. São de bootstrap/operação, não de uso normal.
- **Do próprio tenant** (``/v1/me``): autenticadas por API key. O `tenant_id`
  vem sempre do token, nunca do corpo — é o que impede um tenant de ler ou
  alterar dados de outro.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import exigir_admin, tenant_atual
from app.db.models.tenant import Tenant
from app.db.session import get_session
from app.tenants import repository as repo
from app.tenants import service
from app.tenants.schemas import (
    PaginaTenants,
    RotacionarChaveIn,
    TenantCreate,
    TenantCriadoOut,
    TenantFiscalConfigIn,
    TenantFiscalConfigOut,
    TenantKeyRotacionadaOut,
    TenantOut,
)
from app.tenants.service import SlugJaExiste

HTTP_409 = 409

router = APIRouter(tags=["tenants"])


@router.post(
    "/tenants",
    response_model=TenantCriadoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cria um tenant e devolve a API key (uma única vez)",
    dependencies=[Depends(exigir_admin)],
)
async def criar_tenant(
    dados: TenantCreate,
    db: AsyncSession = Depends(get_session),
) -> TenantCriadoOut:
    try:
        tenant, api_key, webhook_secret = await service.criar_tenant(db, dados)
        await db.commit()
    except SlugJaExiste as exc:
        await db.rollback()
        raise HTTPException(status_code=HTTP_409, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=HTTP_409, detail="violação de unicidade ao criar tenant"
        ) from exc

    base = TenantOut.model_validate(tenant)
    return TenantCriadoOut(
        **base.model_dump(),
        api_key=api_key,
        webhook_secret=webhook_secret,
    )


@router.get(
    "/tenants",
    response_model=PaginaTenants,
    summary="Lista tenants (administrativo)",
    dependencies=[Depends(exigir_admin)],
)
async def listar_tenants(
    limite: int = Query(default=50, ge=1, le=200),
    deslocamento: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
) -> PaginaTenants:
    itens = await repo.listar(db, limite=limite, deslocamento=deslocamento)
    total = await repo.contar(db)
    return PaginaTenants(
        total=total,
        limite=limite,
        deslocamento=deslocamento,
        itens=[TenantOut.model_validate(t) for t in itens],
    )


@router.get("/me", response_model=TenantOut, summary="Dados do tenant autenticado")
async def meu_tenant(tenant: Tenant = Depends(tenant_atual)) -> TenantOut:
    return TenantOut.model_validate(tenant)


@router.post(
    "/me/rotacionar-chave",
    response_model=TenantKeyRotacionadaOut,
    summary="Gera nova API key e invalida a anterior",
)
async def rotacionar_chave(
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
    corpo: RotacionarChaveIn | None = None,
) -> TenantKeyRotacionadaOut:
    """Gera nova chave e define prazo/escopos, se pedido (§73, §75).

    Corpo é opcional: sem ele, o comportamento antigo continua (chave sem prazo e sem restrição).
    """
    atualizado, nova_chave = await service.rotacionar_chave(
        db,
        tenant.id,
        dias_validade=(corpo.dias_validade if corpo else None),
        escopos=([str(e) for e in corpo.escopos] if corpo and corpo.escopos else None),
    )
    await db.commit()
    return TenantKeyRotacionadaOut(
        tenant_id=atualizado.id,
        api_key=nova_chave,
        api_key_prefix=atualizado.api_key_prefix,
        api_key_expira_em=atualizado.api_key_expira_em,
        api_key_escopos=atualizado.api_key_escopos,
    )


@router.put(
    "/me/config-fiscal",
    response_model=TenantFiscalConfigOut,
    summary="Cria ou atualiza a configuração fiscal de um município",
)
async def definir_config_fiscal(
    dados: TenantFiscalConfigIn,
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> TenantFiscalConfigOut:
    payload = dados.model_dump()
    config = await service.definir_config_fiscal(db, tenant.id, payload)
    await db.commit()
    await db.refresh(config)
    return TenantFiscalConfigOut.model_validate(config)


@router.get(
    "/me/config-fiscal",
    response_model=list[TenantFiscalConfigOut],
    summary="Lista as configurações fiscais do tenant",
)
async def listar_config_fiscal(
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
) -> list[TenantFiscalConfigOut]:
    configs = await repo.listar_configs(db, tenant.id)
    return [TenantFiscalConfigOut.model_validate(c) for c in configs]


@router.get(
    "/me/exportacao",
    summary="Exporta os dados do tenant (portabilidade)",
)
async def exportar_dados(
    tenant: Tenant = Depends(tenant_atual),
    db: AsyncSession = Depends(get_session),
    incluir_xml: bool = Query(default=False, description="Inclui o XML dos documentos"),
    limite: int = Query(default=100, ge=1, le=500),
) -> dict:
    """Pacote de dados do próprio tenant, para portabilidade e conferência (§76).

    Inclui: identificação, configuração fiscal, metadados de certificado, webhook e contadores por
    status. O XML só entra com `incluir_xml=true` e até `limite` documentos — exportar tudo por padrão
    transformaria um pedido de conferência em resposta de gigabytes.

    **Nunca inclui:** PFX, senha, hash de chave, segredo de webhook, token de frete. Portabilidade é
    sobre os dados do cliente, não sobre as credenciais dele — e credencial sai do cofre, não de uma
    exportação.
    """
    from sqlalchemy import func

    from app.db.models.invoice import FiscalDocument, Invoice
    from app.db.models.tenant import TenantCertificate, TenantFiscalConfig

    config = (
        await db.execute(
            select(TenantFiscalConfig).where(TenantFiscalConfig.tenant_id == tenant.id)
        )
    ).scalar_one_or_none()

    certificados = (
        (
            await db.execute(
                select(TenantCertificate).where(TenantCertificate.tenant_id == tenant.id)
            )
        )
        .scalars()
        .all()
    )

    contagens = dict(
        (
            await db.execute(
                select(Invoice.status, func.count())
                .where(Invoice.tenant_id == tenant.id)
                .group_by(Invoice.status)
            )
        ).all()
    )

    pacote: dict = {
        "tenant": {
            "id": str(tenant.id),
            "slug": tenant.slug,
            "nome": tenant.nome,
            "status": str(tenant.status),
            "criado_em": tenant.created_at.isoformat() if tenant.created_at else None,
        },
        "configuracao_fiscal": (
            {
                "municipio_ibge": config.municipio_ibge,
                "uf": config.uf,
                "ambiente": str(config.ambiente),
                "serie_dps": config.serie_dps,
                "aliquota_iss": str(config.aliquota_iss),
            }
            if config
            else None
        ),
        "certificados": [
            {
                "id": str(c.id),
                "apelido": c.apelido,
                "cnpj": c.cnpj,
                "valido_ate": c.valido_ate.isoformat() if c.valido_ate else None,
                "fingerprint_sha256": c.fingerprint_sha256,
                "ativo": c.ativo,
            }
            for c in certificados
        ],
        "webhook": {"url": tenant.webhook_url},
        "emissoes_por_status": {str(k): v for k, v in contagens.items()},
    }

    if incluir_xml:
        documentos = (
            (
                await db.execute(
                    select(FiscalDocument)
                    .where(FiscalDocument.tenant_id == tenant.id)
                    .order_by(FiscalDocument.created_at.desc())
                    .limit(limite)
                )
            )
            .scalars()
            .all()
        )
        pacote["documentos"] = [
            {
                "id": str(d.id),
                "tipo": str(d.tipo_documento),
                "chave": d.chave,
                "protocolo": d.protocolo,
                "xml_autorizado": d.xml_autorizado,
            }
            for d in documentos
        ]
        pacote["documentos_limite"] = limite

    return pacote
