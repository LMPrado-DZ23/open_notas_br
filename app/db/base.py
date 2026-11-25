"""Base declarativa e convenção de nomes de constraint.

A convenção de nomes não é cosmética: sem ela, o PostgreSQL gera nomes como
`invoices_tenant_id_fkey1` e o `alembic downgrade` não consegue derrubar a
constraint por nome. Com a convenção, todo índice, FK e unique tem nome
determinístico, o que torna a migração reversível.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

CONVENCAO = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarativa de todos os modelos."""

    metadata = MetaData(naming_convention=CONVENCAO)


class MixinId:
    """Chave primária UUID gerada na aplicação.

    UUID em vez de serial: identificador de recurso fiscal não deve ser adivinhável
    por sequência, e a geração no cliente permite montar o objeto antes do INSERT.
    """

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class MixinTimestamps:
    """Datas de criação e atualização, mantidas pelo banco."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
