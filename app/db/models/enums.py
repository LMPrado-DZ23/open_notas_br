"""Enums persistidos como VARCHAR com CHECK.

`native_enum=False` evita o tipo ENUM nativo do PostgreSQL, que é caro de alterar
(adicionar valor exige DDL e, em versões antigas, lock). Com VARCHAR + CHECK, um
valor novo é uma migração simples de constraint.

`values_callable` garante que o banco guarda o **valor** legível (`"authorized"`),
não o nome do membro (`"AUTHORIZED"`), o que mantém o JSONB e as consultas SQL
coerentes com a API.
"""

from __future__ import annotations

import enum

import sqlalchemy as sa


def coluna_enum[E: enum.Enum](enum_cls: type[E], *, nome: str, tamanho: int = 32) -> sa.Enum:
    """Coluna de enumeração persistida como texto com constraint de validação."""
    return sa.Enum(
        enum_cls,
        name=nome,
        native_enum=False,
        length=tamanho,
        values_callable=lambda x: [membro.value for membro in x],
        validate_strings=True,
    )


class StatusTenant(enum.StrEnum):
    ATIVO = "active"
    SUSPENSO = "suspended"


class StatusFatura(enum.StrEnum):
    """Ciclo de vida da fatura que originará o documento fiscal."""

    PENDENTE = "pending"
    PROCESSANDO = "processing"
    AUTORIZADA = "authorized"
    REJEITADA = "rejected"
    ERRO = "error"
    CANCELADA = "cancelled"


class TipoDocumento(enum.StrEnum):
    NFSE = "nfse"
    NFE = "nfe"
    NFCE = "nfce"
    CTE = "cte"


class AmbienteFiscal(enum.StrEnum):
    HOMOLOGACAO = "homologacao"
    PRODUCAO = "producao"


class ProvedorFiscal(enum.StrEnum):
    """Quem recebe o documento.

    `nacional` é a SEFIN/ADN; `municipal` é o webservice da prefeitura. A escolha
    depende de `aderenteEmissorNacional` do município, MEI e grupo 99 — premissa
    do briefing, não validada contra a lista oficial.
    """

    NACIONAL = "nacional"
    MUNICIPAL = "municipal"


class StatusWebhook(enum.StrEnum):
    PENDENTE = "pending"
    ENTREGUE = "delivered"
    FALHOU = "failed"
    ESGOTADO = "exhausted"


class StatusLote(enum.StrEnum):
    PENDENTE = "pending"
    PROCESSANDO = "processing"
    CONCLUIDO = "completed"
    PARCIAL = "partial"
    FALHOU = "failed"


class StatusApuracao(enum.StrEnum):
    ABERTA = "open"
    FECHADA = "closed"
    PAGA = "paid"
    FALHOU = "failed"


class ProvedorGuia(enum.StrEnum):
    """Provedores de guia de arrecadação.

    Não existe "DART nacional unificado". O que existe é o MAN (que gera DNA) para
    ISS do regime geral, o DAS (regime geral via MAN até 31/12/2032) e a guia
    municipal, quando o município não adere ao padrão nacional.
    """

    MAN = "man"
    DAS = "das"
    MUNICIPAL = "municipal"


class OrigemFatura(enum.StrEnum):
    API = "api"
    DZ23 = "dz23"
    BRIZU = "brizu"
    LOTE = "batch"
    MANUAL = "manual"
