"""Credencial municipal por tenant e município.

Seção 2.1 item 2 do v10.0. Dois pontos delicados concentrados aqui:

**Segredo.** `usuario_ws`, `senha_ws` e `token_ws` são gravados como **ciphertext**
(`LargeBinary`). Quem sela e abre é o serviço, via `app/core/crypto.py` com AAD
vinculado a `tenant_id` + `codigo_ibge` — assim um blob copiado de um tenant para outro
não abre, porque o AAD não confere. Coluna em claro não é opção (R4/P3).

**Numeração.** `ultimo_numero_rps` é incrementado sob `SELECT ... FOR UPDATE`. Sem o
lock, duas emissões simultâneas leem o mesmo número e o município recusa a segunda por
duplicidade — falha intermitente, difícil de reproduzir e que só aparece com carga.
"""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Boolean, ForeignKey, LargeBinary, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, MixinId, MixinTimestamps


class CredencialMunicipalTenant(Base, MixinId, MixinTimestamps):
    """Uma credencial por (tenant, município)."""

    __tablename__ = "credenciais_municipais"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    codigo_ibge: Mapped[str] = mapped_column(
        String(7), ForeignKey("municipios_nfse.codigo_ibge"), nullable=False, index=True
    )

    inscricao_municipal: Mapped[str | None] = mapped_column(String(20))

    #: Ciphertext AES-256-GCM. Nunca texto claro (P3).
    usuario_ws_criptografado: Mapped[bytes | None] = mapped_column(LargeBinary)
    senha_ws_criptografada: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_ws_criptografado: Mapped[bytes | None] = mapped_column(LargeBinary)

    serie_rps_padrao: Mapped[str] = mapped_column(
        String(5), nullable=False, default="1", server_default="1"
    )
    #: Incrementado sob `FOR UPDATE`. BigInt porque RPS não tem teto documentado.
    ultimo_numero_rps: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )

    #: Ativa/desativa sem apagar histórico: credencial revogada não pode ser reusada
    #: por engano, mas apagar perderia a ligação com notas já emitidas.
    ativa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "codigo_ibge", name="uq_credenciais_municipais_tenant_ibge"),
    )

    def __repr__(self) -> str:  # pragma: no cover - diagnóstico
        # Nunca incluir segredo, nem o ciphertext.
        return f"<CredencialMunicipal {self.tenant_id}/{self.codigo_ibge}>"
