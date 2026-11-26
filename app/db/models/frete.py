"""Credencial do Melhor Envio por tenant.

O token do lojista é tão sensível quanto o certificado: quem o tiver compra
etiqueta com o saldo da loja. Por isso é selado com AES-256-GCM usando a mesma
chave-mestra do cofre de certificados, com `aad` amarrado ao tenant — um blob
copiado para outra conta não abre.

Uma linha por tenant: o lojista autoriza uma vez e o sistema renova sozinho. Quando
o `refresh_token` morre (revogação no painel), a linha fica inativa e o lojista
precisa autorizar de novo — a rota de status diz exatamente isso.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, MixinId, MixinTimestamps


class FreteCredencial(Base, MixinId, MixinTimestamps):
    """Tokens OAuth do Melhor Envio, selados, por tenant."""

    __tablename__ = "frete_credenciais"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    #: `access_token` selado (AES-256-GCM). Nunca é devolvido em resposta HTTP.
    access_token_selado: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    #: `refresh_token` selado. Sem ele a renovação é impossível.
    refresh_token_selado: Mapped[bytes | None] = mapped_column(LargeBinary)

    expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escopo: Mapped[str | None] = mapped_column(String(400))
    #: Guarda o ambiente usado na autorização: sandbox e produção não se misturam.
    sandbox: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    ativo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    #: Última renovação bem-sucedida, para diagnóstico.
    renovado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
