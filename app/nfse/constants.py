"""Constantes do Sistema Nacional NFS-e (leiaute 1.01 e janela da NT 009).

Fonte das URLs e das rotas: implementação de referência em Python analisada em
`docs/REFERENCIAS.md` (seção 1). Não há, nesta execução, acesso à documentação
oficial — por isso cada fato carrega etiqueta e a URL base é sempre
sobrescrevível por variável de ambiente.

A janela temporal abaixo é a informação mais perigosa de errar: hoje a produção
usa um leiaute e a homologação já usa outro.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone, tzinfo
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.db.models.enums import AmbienteFiscal

logger = logging.getLogger(__name__)

#: Namespace do XML da NFS-e nacional. [CONFIRMADO] na referência.
NS_NFSE = "http://www.sped.fazenda.gov.br/nfse"
NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"

#: Versão do leiaute. [CONFIRMADO] na referência.
VERSAO_LEIAUTE = "1.01"

#: Faixa de série permitida para emissão por API. Fora dela: rejeição E0010.
#: [CONFIRMADO] na referência.
SERIE_API_MIN = 1
SERIE_API_MAX = 49_999

#: Consulta pública de uma NFS-e pela chave (abre no navegador).
URL_CONSULTA_PUBLICA = "https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave={chave}"

#: Hosts oficiais. Usado como allowlist: o cliente recusa falar com outro host,
#: para que um override de ambiente mal configurado não envie DPS assinada para
#: um servidor desconhecido.
HOSTS_OFICIAIS = ("nfse.gov.br", "producaorestrita.nfse.gov.br")

#: URLs da SEFIN Nacional. [CONFIRMADO] na referência; [A VALIDAR] contra
#: documentação oficial, porque a referência também não cita fonte primária.
SEFIN_PRODUCAO = "https://sefin.nfse.gov.br/SefinNacional"
SEFIN_HOMOLOGACAO = "https://sefin.producaorestrita.nfse.gov.br/SefinNacional"

#: URLs do ADN (Ambiente de Dados Nacional): distribuição e parametrização.
ADN_PRODUCAO = "https://adn.nfse.gov.br"
ADN_HOMOLOGACAO = "https://adn.producaorestrita.nfse.gov.br"


def _fuso_brasil() -> tzinfo:
    """Fuso de Brasília, com fallback explícito.

    O `zoneinfo` do Windows depende do pacote `tzdata` (dependência declarada em
    `pyproject.toml`). Se ele faltar mesmo assim, o fallback é UTC-3 fixo — que é
    exato na prática desde o fim do horário de verão brasileiro em 2019, mas não
    é a mesma coisa que um fuso IANA. O aviso no log evita que a diferença passe
    silenciosa.
    """
    try:
        return ZoneInfo("America/Sao_Paulo")
    except ZoneInfoNotFoundError:  # pragma: no cover - ambiente sem tzdata
        logger.warning(
            "tzdata ausente: usando UTC-3 fixo. Instale `tzdata` para fuso IANA correto."
        )
        return timezone(timedelta(hours=-3), "America/Sao_Paulo")


FUSO_BR = _fuso_brasil()


def tp_amb(ambiente: AmbienteFiscal) -> str:
    """``tpAmb`` da DPS: 1 = produção, 2 = homologação (Produção Restrita)."""
    return "1" if ambiente is AmbienteFiscal.PRODUCAO else "2"


def sefin_url(ambiente: AmbienteFiscal) -> str:
    """URL base da SEFIN Nacional para o ambiente."""
    return SEFIN_PRODUCAO if ambiente is AmbienteFiscal.PRODUCAO else SEFIN_HOMOLOGACAO


def adn_url(ambiente: AmbienteFiscal) -> str:
    """URL base do ADN para o ambiente."""
    return ADN_PRODUCAO if ambiente is AmbienteFiscal.PRODUCAO else ADN_HOMOLOGACAO


def host_permitido(url: str, *, permitir_override: bool = False) -> bool:
    """True se a URL aponta para um host oficial (ou override foi autorizado).

    O override existe para desenvolvimento e para espelhos internos; sem ele, uma
    variável de ambiente errada mandaria DPS assinada para terceiros.
    """
    if permitir_override:
        return url.startswith(("http://", "https://"))
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    return any(host == oficial or host.endswith(f".{oficial}") for oficial in HOSTS_OFICIAIS)


# ---------------------------------------------------------------------------
# Janela de leiaute (NT 009)
# ---------------------------------------------------------------------------
# A NT 009 acrescenta `finNFSe` em `infDPS`, CST/cClassTrib em
# `IBSCBS/valores/trib` e `vAjusteBC`. Entrou na Produção Restrita (homologação)
# em 20/10/2026 e entra na Produção em 01/12/2026; o leiaute anterior vale na
# produção até 30/11/2026. [CONFIRMADO] na referência (comunicado CGNFS-e de
# 20/10/2026 citado lá); [A VALIDAR] contra o comunicado oficial.
LEIAUTE_ANTERIOR = "v1_01"
LEIAUTE_NT009 = "v1_01_nt009"
INICIO_NT009_PRODUCAO = datetime(2026, 12, 1, tzinfo=FUSO_BR)


def leiaute(ambiente: AmbienteFiscal, quando: datetime | None = None) -> str:
    """Identificador do leiaute vigente no ambiente, na data informada.

    Homologação já está inteira na NT 009. Produção muda em 01/12/2026. Sem data,
    usa agora — e é por isso que o `quando` é explícito no teste: a resposta muda
    de acordo com o dia.
    """
    if ambiente is AmbienteFiscal.HOMOLOGACAO:
        return LEIAUTE_NT009
    momento = quando or datetime.now(FUSO_BR)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=FUSO_BR)
    return LEIAUTE_NT009 if momento >= INICIO_NT009_PRODUCAO else LEIAUTE_ANTERIOR


class TipoEvento(StrEnum):
    """Tipos de evento da NFS-e nacional.

    [INFERIDO] a partir da nomenclatura usada na referência; os códigos exatos
    aceitos pela SEFIN precisam de confirmação em homologação.
    """

    CANCELAMENTO = "CANCELAMENTO"
    CANCELAMENTO_POR_SUBSTITUICAO = "CANCELAMENTO_POR_SUBSTITUICAO"
    CONFIRMACAO = "CONFIRMACAO"
    REJEICAO = "REJEICAO"
    ANULACAO_REJEICAO = "ANULACAO_REJEICAO"
