"""Catálogo dos 16 tipos de evento da NFS-e, extraído do XSD oficial.

**O que este módulo codifica**: a *estrutura* que o schema exige — nome do grupo,
campos, obrigatoriedade e tipo de cada campo. Isso é `[CONFIRMADO]`, porque veio de
`tiposEventos_v1.01.xsd` (versionado em `tests/fixtures/schemas/nfse-1.01/`).

**O que este módulo NÃO codifica**: o significado de negócio de cada evento. As
descrições em `descricao` são `[INFERIDO]` do nome do grupo e do uso corrente, não
de fonte oficial. Quem dispara um evento responde pelo enquadramento — o código não
escolhe por ninguém.

Por que data-driven e não 16 builders à mão: a estrutura está no schema e muda com
ele; reescrever 16 construtores a cada leiaute novo multiplicaria a chance de erro.
O que é difícil e específico (qual motivo, qual processo) continua sendo decisão de
quem chama.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.nfse.constants import NS_NFSE, VERSAO_LEIAUTE

#: Restrições lidas do schema, por tipo de campo.
RESTRICOES: dict[str, dict[str, object]] = {
    "TSMotivo": {"min": 15, "max": 255},
    "TSCPF": {"pattern": r"[0-9]{11}"},
    "TSChaveNFSe": {"pattern": r"[0-9]{6}[0-9A-Z]{14}[0-9]{30}"},
    "TSNumProcAdmAnaliseFiscalCanc": {"pattern": r"[0-9]{1,30}"},
    "TSIdNumEvento": {"pattern": r"[0-9]{8}(1[0-9]{14}|2[0-9A-Z]{14})[0-9]{33}"},
    "TSCodJustCanc": {"enum": ("1", "2", "9")},
    "TSCodJustSubst": {"enum": ("01", "02", "03", "04", "05", "99")},
    "TSCodJustAnaliseFiscalCanc": {"enum": ("1", "2", "9")},
    "TSCodJustAnaliseFiscalCancDef": {"enum": ("1",)},
    "TSCodJustAnaliseFiscalCancIndef": {"enum": ("1", "2")},
    "TSCodMotivoRejeicao": {"enum": ("1", "2", "3", "4", "5", "9")},
    "TSCodigoEventoNFSe": {"enum": ("e101101", "e105102", "e105104", "e105105", "e305101")},
}


@dataclass(frozen=True, slots=True)
class CampoEvento:
    nome: str
    tipo: str
    obrigatorio: bool = True


@dataclass(frozen=True, slots=True)
class TipoEvento:
    codigo: str
    descricao: str  # [INFERIDO] do nome do grupo / uso corrente
    campos: tuple[CampoEvento, ...]

    @property
    def grupo(self) -> str:
        return f"e{self.codigo}"

    @property
    def obrigatorios(self) -> tuple[str, ...]:
        return tuple(c.nome for c in self.campos if c.obrigatorio)


def _campos(*definicoes: tuple[str, str] | tuple[str, str, bool]) -> tuple[CampoEvento, ...]:
    saida = []
    for item in definicoes:
        nome, tipo = item[0], item[1]
        obrigatorio = item[2] if len(item) > 2 else True
        saida.append(CampoEvento(nome=nome, tipo=tipo, obrigatorio=obrigatorio))
    return tuple(saida)


#: Descrição fixa por tipo (`xDesc`), **[CONFIRMADO]** no XSD — não é sugestão.
#: Catálogo completo, na ordem em que o leiaute os define.
TIPOS_EVENTO: dict[str, TipoEvento] = {
    "101101": TipoEvento(
        "101101",
        "Cancelamento de NFS-e (por iniciativa do emitente)",
        _campos(
            ("cMotivo", "TSCodJustCanc"),
            ("xMotivo", "TSMotivo"),
        ),
    ),
    "105102": TipoEvento(
        "105102",
        "Cancelamento por substituição (com chave substituta)",
        _campos(
            ("cMotivo", "TSCodJustSubst"),
            ("xMotivo", "TSMotivo", False),
            ("chSubstituta", "TSChaveNFSe"),
        ),
    ),
    "101103": TipoEvento(
        "101103",
        "Cancelamento em análise fiscal (por decisão do fisco)",
        _campos(
            ("cMotivo", "TSCodJustAnaliseFiscalCanc"),
            ("xMotivo", "TSMotivo"),
        ),
    ),
    "105104": TipoEvento(
        "105104",
        "Análise fiscal com deferimento",
        _campos(
            ("CPFAgTrib", "TSCPF"),
            ("nProcAdm", "TSNumProcAdmAnaliseFiscalCanc", False),
            ("cMotivo", "TSCodJustAnaliseFiscalCancDef"),
            ("xMotivo", "TSMotivo"),
        ),
    ),
    "105105": TipoEvento(
        "105105",
        "Análise fiscal com indeferimento",
        _campos(
            ("CPFAgTrib", "TSCPF"),
            ("nProcAdm", "TSNumProcAdmAnaliseFiscalCanc", False),
            ("cMotivo", "TSCodJustAnaliseFiscalCancIndef"),
            ("xMotivo", "TSMotivo"),
        ),
    ),
    "202201": TipoEvento("202201", "Confirmação de serviço (prestador)", _campos()),
    "203202": TipoEvento("203202", "Confirmação de serviço (tomador)", _campos()),
    "204203": TipoEvento("204203", "Confirmação de serviço (intermediário)", _campos()),
    "205204": TipoEvento("205204", "Confirmação de serviço (outro)", _campos()),
    "202205": TipoEvento(
        "202205",
        "Rejeição de serviço (prestador)",
        _campos(
            ("cMotivo", "TSCodMotivoRejeicao"),
            ("xMotivo", "TSMotivo", False),
        ),
    ),
    "203206": TipoEvento(
        "203206",
        "Rejeição de serviço (tomador)",
        _campos(
            ("cMotivo", "TSCodMotivoRejeicao"),
            ("xMotivo", "TSMotivo", False),
        ),
    ),
    "204207": TipoEvento(
        "204207",
        "Rejeição de serviço (intermediário)",
        _campos(
            ("cMotivo", "TSCodMotivoRejeicao"),
            ("xMotivo", "TSMotivo", False),
        ),
    ),
    "205208": TipoEvento(
        "205208",
        "Rejeição de manifesto de rejeição",
        _campos(
            ("CPFAgTrib", "TSCPF"),
            ("idEvManifRej", "TSIdNumEvento"),
            ("xMotivo", "TSMotivo"),
        ),
    ),
    "305101": TipoEvento(
        "305101",
        "Bloqueio ofício (por processo administrativo)",
        _campos(
            ("CPFAgTrib", "TSCPF"),
            ("nProcAdm", "TSNumProcAdmAnaliseFiscalCanc"),
            ("xProcAdm", "TSMotivo"),
        ),
    ),
    "305102": TipoEvento(
        "305102",
        "Evento ofício genérico",
        _campos(
            ("CPFAgTrib", "TSCPF"),
            ("codEvento", "TSCodigoEventoNFSe"),
            ("xMotivo", "TSMotivo"),
        ),
    ),
    "305103": TipoEvento(
        "305103",
        "Desbloqueio ofício",
        _campos(
            ("CPFAgTrib", "TSCPF"),
            ("idBloqOfic", "TSIdNumEvento"),
        ),
    ),
}

#: Tipos operados pelo contribuinte (os demais são de ofício/fisco).
TIPOS_DO_CONTRIBUINTE = (
    "101101",
    "105102",
    "202201",
    "203202",
    "204203",
    "205204",
    "202205",
    "203206",
    "204207",
)


X_DESC = {
    "101101": "Cancelamento de NFS-e",
    "105102": "Cancelamento de NFS-e por Substituição",
    "101103": "Solicitação de Análise Fiscal para Cancelamento de NFS-e",
    "105104": "Cancelamento de NFS-e Deferido por Análise Fiscal",
    "105105": "Cancelamento de NFS-e Indeferido por Análise Fiscal",
    "202201": "Manifestação de NFS-e - Confirmação do Prestador",
    "203202": "Manifestação de NFS-e - Confirmação do Tomador",
    "204203": "Manifestação de NFS-e - Confirmação do Intermediário",
    "205204": "Manifestação de NFS-e - Confirmação Tácita",
    "202205": "Manifestação de NFS-e - Rejeição do Prestador",
    "203206": "Manifestação de NFS-e - Rejeição do Tomador",
    "204207": "Manifestação de NFS-e - Rejeição do Intermediário",
    "205208": "Manifestação de NFS-e - Anulação da Rejeição",
    "305101": "Cancelamento de NFS-e por Ofício",
    "305102": "Bloqueio de NFS-e por Ofício",
    "305103": "Desbloqueio de NFS-e por Ofício",
}


class ErroDeEventoCatalogo(Exception):
    """Evento fora do catálogo ou campo inválido."""


def obter_tipo(codigo: str) -> TipoEvento:
    achado = TIPOS_EVENTO.get(codigo)
    if achado is None:
        raise ErroDeEventoCatalogo(
            f"tipo de evento {codigo!r} não existe no leiaute 1.01. "
            f"Disponíveis: {', '.join(sorted(TIPOS_EVENTO))}"
        )
    return achado


def validar_campo(nome_campo: str, tipo: str, valor: str) -> None:
    """Valida um valor contra as restrições do schema, com mensagem local.

    Por que validar aqui se o XSD valida: a mensagem do lxml fala em *facet* e
    número de linha do XML gerado, o que não ajuda quem preencheu o formulário.
    Aqui a mensagem diz o campo e a regra.
    """
    regra = RESTRICOES.get(tipo, {})

    if valor is None or str(valor).strip() == "":
        raise ErroDeEventoCatalogo(f"campo {nome_campo} não pode ser vazio")

    texto = str(valor)
    if "enum" in regra:
        aceitos = regra["enum"]
        if texto not in aceitos:
            raise ErroDeEventoCatalogo(
                f"campo {nome_campo} aceita {', '.join(aceitos)}; recebeu {texto!r}"
            )
    if "pattern" in regra and not re.fullmatch(str(regra["pattern"]), texto):
        raise ErroDeEventoCatalogo(
            f"campo {nome_campo} não casa com o padrão do leiaute: {regra['pattern']}"
        )
    if "min" in regra and len(texto) < int(regra["min"]):
        raise ErroDeEventoCatalogo(
            f"campo {nome_campo} exige ao menos {regra['min']} caracteres; tem {len(texto)}"
        )
    if "max" in regra and len(texto) > int(regra["max"]):
        raise ErroDeEventoCatalogo(
            f"campo {nome_campo} aceita no máximo {regra['max']} caracteres; tem {len(texto)}"
        )


def _escapar(valor: str) -> str:
    return (
        str(valor)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def construir_evento(
    codigo: str,
    *,
    chave: str,
    cnpj_autor: str,
    campos: dict[str, str],
    ambiente: str = "2",
    dh_evento: str,
    ver_aplic: str = "notasbr-1.0",
) -> bytes:
    """Monta o `pedRegEvento` genérico, validando os campos do catálogo.

    `dh_evento` já vem formatada (`AAAA-MM-DDTHH:MM:SS+00:00`) — quem converte é o
    chamador, que sabe o fuso do fato.
    """
    tipo = obter_tipo(codigo)
    if ambiente not in ("1", "2"):
        raise ErroDeEventoCatalogo("tpAmb deve ser '1' ou '2'")
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", cnpj_autor):
        raise ErroDeEventoCatalogo(f"CNPJAutor inválido: {cnpj_autor!r}")
    if not re.fullmatch(r"[0-9]{6}[0-9A-Z]{14}[0-9]{30}", chave):
        raise ErroDeEventoCatalogo("chave da NFS-e fora do padrão do leiaute")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([-+]\d{2}:\d{2})", dh_evento):
        raise ErroDeEventoCatalogo(
            "dhEvento deve ser AAAA-MM-DDTHH:MM:SS±HH:MM "
            "(o leiaute não aceita 'Z', apesar do tipo se chamar TSDateTimeUTC)"
        )

    faltando = [nome for nome in tipo.obrigatorios if nome not in campos]
    if faltando:
        raise ErroDeEventoCatalogo(f"evento {codigo} exige os campos {', '.join(faltando)}")
    desconhecidos = set(campos) - {c.nome for c in tipo.campos}
    if desconhecidos:
        raise ErroDeEventoCatalogo(
            f"evento {codigo} não tem os campos {', '.join(sorted(desconhecidos))}"
        )

    for definicao in tipo.campos:
        if definicao.nome in campos:
            validar_campo(definicao.nome, definicao.tipo, campos[definicao.nome])

    # `xDesc` não é texto livre: o schema enumera uma descrição por tipo de evento.
    # Emitir a oficial é obrigatório; deixar o chamador escrever produz recusa.
    corpo_campos = f"<xDesc>{_escapar(X_DESC[codigo])}</xDesc>" + "".join(
        f"<{d.nome}>{_escapar(campos[d.nome])}</{d.nome}>" for d in tipo.campos if d.nome in campos
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<pedRegEvento xmlns="{NS_NFSE}" versao="{VERSAO_LEIAUTE}">'
        f'<infPedReg Id="PRE{chave}{codigo}">'
        f"<tpAmb>{ambiente}</tpAmb>"
        f"<verAplic>{_escapar(ver_aplic)}</verAplic>"
        f"<dhEvento>{dh_evento}</dhEvento>"
        f"<CNPJAutor>{cnpj_autor}</CNPJAutor>"
        f"<chNFSe>{chave}</chNFSe>"
        f"<{tipo.grupo}>{corpo_campos}</{tipo.grupo}>"
        "</infPedReg>"
        "</pedRegEvento>"
    ).encode()
