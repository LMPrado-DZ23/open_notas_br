"""Pedido de registro de evento da NFS-e — cancelamento.

Estrutura tirada do **XSD oficial**, não de memória (`tiposEventos_v1.01.xsd`,
versionado em `tests/fixtures/schemas/nfse-1.01/`):

`pedRegEvento` → `infPedReg` (atributo `Id`) com

    tpAmb, verAplic, dhEvento, CNPJAutor | CPFAutor, chNFSe,
    e101101 { xDesc, cMotivo, xMotivo }        ← cancelamento
    ds:Signature

Restrições **lidas do schema**:

| Campo | Regra |
|---|---|
| `infPedReg/@Id` | `PRE` + chave (50) + tipo do evento (6) = **59** |
| `evento/@Id` (retorno) | `EVT` + chave (50) + tipo (6) + nPedReg (3) = 62 |
| `tpAmb` | `1` (produção) ou `2` (homologação) |
| `verAplic` | 1 a 20 caracteres |
| `chNFSe` | 50 caracteres: `[0-9]{6}[0-9A-Z]{14}[0-9]{30}` |
| `cMotivo` | `1`, `2` ou `9` |
| `xMotivo` | 15 a 255 caracteres |

Os **significados** de `cMotivo` (1/2/9) não estão no XSD: são **[INFERIDO]** do
leiaute e do uso corrente. Quem cancela deve conferir o enquadramento com o
contador — o código não escolhe motivo por você.

O evento é assinado como o resto: XMLDSig enveloped, SHA-256, C14N exclusiva,
`Signature` sem prefixo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from app.nfse.constants import NS_NFSE, VERSAO_LEIAUTE

#: Código do evento de cancelamento no leiaute 1.01.
TIPO_CANCELAMENTO = "101101"

#: Nome do grupo do evento no XML.
GRUPO_CANCELAMENTO = f"e{TIPO_CANCELAMENTO}"

#: Motivos aceitos pelo schema. Descrições **[INFERIDO]** do uso corrente.
MOTIVOS_CANCELAMENTO: dict[str, str] = {
    "1": "Erro na emissão",
    "2": "Serviço não prestado",
    "9": "Outros",
}

X_MOTIVO_MIN = 15
X_MOTIVO_MAX = 255
CHAVE_TAMANHO = 50


class ErroDeEvento(Exception):
    """Pedido de evento inválido segundo o leiaute."""


def id_pedido_evento(chave: str, tipo: str) -> str:
    """`Id` do **pedido** de registro: `PRE` + chave (50) + tipo do evento (6) = 59.

    Confirmado no XSD pelo pattern `PRE[0-9]{8}(1[0-9]{14}|2[0-9A-Z]{14})[0-9]{33}`
    e `maxLength` 59.

    Cuidado que o schema revelou: existe **outro** identificador, com prefixo
    `EVT` e 62 caracteres (`TSIdEvento`), que carrega também o `nPedRegEvento` de
    3 dígitos. Ele pertence ao **evento já registrado**, não ao pedido. Usar `EVT`
    aqui faz o pedido ser recusado por `maxLength` — erro que só aparece na
    validação, não na leitura do nome do campo.
    """
    _validar_chave_e_tipo(chave, tipo)
    return f"PRE{chave}{tipo}"


def id_evento_registrado(chave: str, tipo: str, sequencia: int) -> str:
    """`Id` do evento **registrado**: `EVT` + chave (50) + tipo (6) + nPedReg (3).

    É o identificador que volta no XML autorizado do evento (tipo `TSIdEvento`,
    62 caracteres). Serve para conferir o retorno, não para montar o pedido.
    """
    _validar_chave_e_tipo(chave, tipo)
    if not 1 <= sequencia <= 999:
        raise ErroDeEvento(f"sequência do evento deve ficar entre 1 e 999; recebeu {sequencia}")
    return f"EVT{chave}{tipo}{sequencia:03d}"


def _validar_chave_e_tipo(chave: str, tipo: str) -> None:
    if len(chave) != CHAVE_TAMANHO:
        raise ErroDeEvento(f"chave da NFS-e deve ter {CHAVE_TAMANHO} caracteres; tem {len(chave)}")
    if not re.fullmatch(r"[0-9]{6}[0-9A-Z]{14}[0-9]{30}", chave):
        raise ErroDeEvento(
            "chave fora do padrão do leiaute: 6 dígitos + 14 alfanuméricos (CNPJ) + 30 dígitos"
        )
    if not re.fullmatch(r"\d{6}", tipo):
        raise ErroDeEvento(f"tipo de evento deve ter 6 dígitos; recebeu {tipo!r}")


@dataclass(slots=True)
class PedidoCancelamento:
    """Dados de um pedido de cancelamento."""

    chave: str
    cnpj_autor: str
    c_motivo: str
    x_motivo: str
    ambiente: str = "2"  # 2 = homologação
    sequencia: int = 1
    dh_evento: datetime | None = None
    ver_aplic: str = "notasbr-1.0"

    def validar(self) -> None:
        """Valida contra as regras do schema, com mensagem melhor que a da SEFIN."""
        id_pedido_evento(self.chave, TIPO_CANCELAMENTO)

        if self.ambiente not in ("1", "2"):
            raise ErroDeEvento(
                f"tpAmb deve ser '1' (produção) ou '2' (homologação); recebeu {self.ambiente!r}"
            )

        if not 1 <= len(self.ver_aplic) <= 20:
            raise ErroDeEvento("verAplic deve ter de 1 a 20 caracteres")

        if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", self.cnpj_autor):
            raise ErroDeEvento(f"CNPJAutor inválido: {self.cnpj_autor!r}")

        if self.c_motivo not in MOTIVOS_CANCELAMENTO:
            aceitos = ", ".join(sorted(MOTIVOS_CANCELAMENTO))
            raise ErroDeEvento(f"cMotivo deve ser um de {aceitos}; recebeu {self.c_motivo!r}")

        if not X_MOTIVO_MIN <= len(self.x_motivo) <= X_MOTIVO_MAX:
            raise ErroDeEvento(
                f"xMotivo deve ter de {X_MOTIVO_MIN} a {X_MOTIVO_MAX} caracteres; "
                f"tem {len(self.x_motivo)}. Texto curto é recusado pela SEFIN, não "
                "pelo nosso código."
            )


def _escapar(valor: str) -> str:
    return (
        valor.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def construir_pedido_evento(pedido: PedidoCancelamento) -> bytes:
    """Monta o XML do `pedRegEvento` (sem assinatura)."""
    pedido.validar()
    from datetime import UTC

    momento = pedido.dh_evento or datetime.now(UTC)
    if momento.tzinfo is None:
        raise ErroDeEvento(
            "dhEvento precisa de fuso: o leiaute exige UTC (TSDateTimeUTC) e "
            "horário sem fuso seria interpretado como local do servidor"
        )
    # Atenção: apesar do nome `TSDateTimeUTC`, o pattern do XSD NÃO aceita `Z`.
    # Ele exige offset numérico com minutos zerados (`-03:00`, `+00:00`). Emitir
    # `Z` é recusado pelo schema — descoberto validando, não lendo o nome do tipo.
    dh_evento = momento.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    identificador = id_pedido_evento(pedido.chave, TIPO_CANCELAMENTO)

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<pedRegEvento xmlns="{NS_NFSE}" versao="{VERSAO_LEIAUTE}">'
        f'<infPedReg Id="{identificador}">'
        f"<tpAmb>{pedido.ambiente}</tpAmb>"
        f"<verAplic>{_escapar(pedido.ver_aplic)}</verAplic>"
        f"<dhEvento>{dh_evento}</dhEvento>"
        f"<CNPJAutor>{pedido.cnpj_autor}</CNPJAutor>"
        f"<chNFSe>{pedido.chave}</chNFSe>"
        f"<{GRUPO_CANCELAMENTO}>"
        "<xDesc>Cancelamento de NFS-e</xDesc>"
        f"<cMotivo>{pedido.c_motivo}</cMotivo>"
        f"<xMotivo>{_escapar(pedido.x_motivo)}</xMotivo>"
        f"</{GRUPO_CANCELAMENTO}>"
        "</infPedReg>"
        "</pedRegEvento>"
    ).encode()


def assinar_pedido_evento(xml: bytes, certificado) -> bytes:
    """Assina o `pedRegEvento` no padrão do projeto (enveloped, SHA-256, C14N exc.).

    Delega ao assinador único do projeto: um segundo caminho de assinatura seria
    uma segunda oportunidade de errar C14N ou prefixo de `Signature`.
    """
    from app.nfse.signer import assinar_bytes

    # `assinar_bytes` resolve a referência pelo atributo `Id` do documento, que aqui
    # é o `infPedReg`. Não há parâmetro de referência: o assinador já busca o `Id`.
    return assinar_bytes(xml, certificado)
