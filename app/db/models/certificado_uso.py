"""Registro de uso do certificado: quem usou qual A1, quando e para qual operação.

**Por que existe.** O cofre guarda o certificado, mas não havia como responder "este A1 foi usado
para quê, e quando?" — pergunta obrigatória para operar credencial fiscal de terceiros (o cliente é o
emitente). Sem registro, um uso indevido é indetectável, e a resposta a incidente começa no escuro.

**O que NÃO é guardado, por construção:** PFX, senha, XML, payload, dado pessoal. A linha registra
`operacao`, `ambiente`, `sucesso` e o **tipo** do erro (nunca a mensagem, que pode conter dado do
cliente). Sem isso, a auditoria viraria um segundo vazamento.

Retenção: a tabela cresce com o uso. Não há expurgo automático — decisão do operador, coerente com
`docs/OPERACAO.md` §7, que já declara essa ausência.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, MixinId, MixinTimestamps


class CertificadoUso(Base, MixinId, MixinTimestamps):
    """Uma abertura do certificado para uso fiscal."""

    __tablename__ = "certificado_usos"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    certificado_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenant_certificates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Operação fiscal que exigiu a chave (`emissao`, `cancelamento`, `evento`, `status_transporte`).
    operacao: Mapped[str] = mapped_column(String(40), nullable=False)
    #: `homologacao` ou `producao` — separa teste de operação real no próprio registro.
    ambiente: Mapped[str | None] = mapped_column(String(20))
    #: Se a abertura falhou (chave-mestra trocada, envelope corrompido), fica registrado.
    sucesso: Mapped[bool] = mapped_column(nullable=False, default=True)
    #: Nome da classe da exceção, nunca a mensagem: mensagem pode carregar dado do cliente.
    erro_tipo: Mapped[str | None] = mapped_column(String(80))

    __table_args__ = (Index("ix_certificado_usos_tenant_criado", "tenant_id", "created_at"),)

    def __repr__(self) -> str:  # pragma: no cover - conveniência de depuração
        return f"<CertificadoUso {self.operacao} ok={self.sucesso}>"
