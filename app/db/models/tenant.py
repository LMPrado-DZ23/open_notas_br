"""Tenant, suas configurações fiscais e seus certificados A1.

O tenant é a fronteira de isolamento de todo o sistema. Nenhuma consulta de
recurso fiscal pode sair daqui sem `tenant_id` no filtro.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, MixinId, MixinTimestamps
from app.db.models.enums import (
    AmbienteFiscal,
    ProvedorFiscal,
    StatusTenant,
    coluna_enum,
)


class Tenant(Base, MixinId, MixinTimestamps):
    """Conta isolada. Cada tenant tem suas próprias notas, certificados e guias."""

    __tablename__ = "tenants"

    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    email_contato: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[StatusTenant] = mapped_column(
        coluna_enum(StatusTenant, nome="status_tenant"),
        nullable=False,
        default=StatusTenant.ATIVO,
        server_default=StatusTenant.ATIVO.value,
    )

    # Credencial: guardamos apenas hash e um prefixo visível para identificação.
    api_key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    api_key_rotacionada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Quando a chave atual deixa de valer por tempo (`NULL` = sem prazo).
    api_key_expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Quando a chave foi **revogada** (vazamento, desligamento). Revogar grava um hash aleatório
    #: inutilizável, então a chave antiga deixa de casar até na busca do próprio dono.
    api_key_revogada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Endpoint e segredo de webhook de saída. O segredo é selado (AES-256-GCM).
    webhook_url: Mapped[str | None] = mapped_column(String(500))
    webhook_secret_selado: Mapped[bytes | None] = mapped_column(LargeBinary)

    configuracoes: Mapped[list[TenantFiscalConfig]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan", lazy="selectin"
    )
    certificados: Mapped[list[TenantCertificate]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("api_key_hash", name="uq_tenants_api_key_hash"),
        Index("ix_tenants_status", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - depuração
        return f"<Tenant {self.slug}>"


class TenantFiscalConfig(Base, MixinId, MixinTimestamps):
    """Parâmetros fiscais do tenant para um município e ambiente.

    Um tenant pode emitir para mais de um município; por isso a chave natural é
    ``(tenant_id, municipio_ibge, ambiente)``.
    """

    __tablename__ = "tenant_fiscal_configs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    municipio_ibge: Mapped[str] = mapped_column(String(7), nullable=False)
    municipio_nome: Mapped[str | None] = mapped_column(String(120))
    uf: Mapped[str | None] = mapped_column(String(2))

    # [A VALIDAR] A lista oficial de municípios aderentes não foi verificada.
    # Decisão de rota: `aderente=True` -> SEFIN; `False` -> municipal, exceto MEI
    # e itens do grupo 99, que vão sempre para a SEFIN (premissa do briefing).
    aderente_emissor_nacional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    provedor: Mapped[ProvedorFiscal] = mapped_column(
        coluna_enum(ProvedorFiscal, nome="provedor_fiscal"),
        nullable=False,
        default=ProvedorFiscal.NACIONAL,
        server_default=ProvedorFiscal.NACIONAL.value,
    )
    ambiente: Mapped[AmbienteFiscal] = mapped_column(
        coluna_enum(AmbienteFiscal, nome="ambiente_fiscal"),
        nullable=False,
        default=AmbienteFiscal.HOMOLOGACAO,
        server_default=AmbienteFiscal.HOMOLOGACAO.value,
    )

    # Regime: CRT 1/2/4 = Simples/MEI, 3 = regime normal.
    regime_tributario: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    simples_nacional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    optante_mei: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    aliquota_iss: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))

    serie_dps: Mapped[str] = mapped_column(String(5), nullable=False, default="1")
    proximo_numero_dps: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    inscricao_municipal: Mapped[str | None] = mapped_column(String(30))
    cnae_principal: Mapped[str | None] = mapped_column(String(9))
    codigo_tributacao_nacional: Mapped[str | None] = mapped_column(String(10))

    # Campos que ainda não têm coluna própria e o layout exige.
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    tenant: Mapped[Tenant] = relationship(back_populates="configuracoes")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "municipio_ibge",
            "ambiente",
            name="uq_tenant_fiscal_configs_tenant_municipio_ambiente",
        ),
        Index("ix_tenant_fiscal_configs_tenant_ambiente", "tenant_id", "ambiente"),
    )


class TenantCertificate(Base, MixinId, MixinTimestamps):
    """Certificado digital A1 selado com AES-256-GCM.

    O PFX em claro **nunca** é persistido e **nunca** é logado. A coluna
    `pfx_selado` contém apenas o envelope; a abertura acontece em memória, no
    momento da assinatura.
    """

    __tablename__ = "tenant_certificates"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    apelido: Mapped[str] = mapped_column(String(100), nullable=False)
    # CNPJ alfanumérico (julho/2026) cabe aqui: 14 caracteres + margem.
    cnpj: Mapped[str | None] = mapped_column(String(20))
    subject_cn: Mapped[str | None] = mapped_column(String(255))
    emissor: Mapped[str | None] = mapped_column(String(255))
    numero_serie: Mapped[str | None] = mapped_column(String(120))
    valido_de: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valido_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fingerprint_sha256: Mapped[str | None] = mapped_column(String(64))

    pfx_selado: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    senha_selada: Mapped[bytes | None] = mapped_column(LargeBinary)
    ativo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    tenant: Mapped[Tenant] = relationship(back_populates="certificados")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "fingerprint_sha256", name="uq_tenant_certificates_tenant_fingerprint"
        ),
        Index("ix_tenant_certificates_tenant_ativo", "tenant_id", "ativo"),
        Index("ix_tenant_certificates_valido_ate", "valido_ate"),
    )
