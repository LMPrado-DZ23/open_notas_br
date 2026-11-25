"""Leitura de XML fiscal sem se machucar.

Duas preocupações concretas:

1. **Entidade externa / expansão de entidade.** O `ElementTree` da stdlib não
   busca DTD externo, mas ainda é exposto a expansão de entidades internas
   ("billion laughs"). Como XML fiscal nunca precisa de `DOCTYPE`, a defesa é
   recusar o documento quando ele aparece. É barato e determinístico.
2. **Navegação por namespace.** NF-e e CT-e usam *default namespace*, e há
   emissores que trocam prefixo. Por isso toda navegação aqui compara o **nome
   local** da tag, não o nome qualificado.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from xml.etree import ElementTree as ET

from .erros import ArquivoGrandeDemais, XmlInvalido

#: 20 MiB. Um XML de NF-e normal fica na casa de dezenas de KB.
LIMITE_PADRAO_BYTES = 20 * 1024 * 1024

_MARCAS_PROIBIDAS = (b"<!DOCTYPE", b"<!ENTITY")

_ESPACOS = re.compile(r"\s+")


def parse_seguro(dados: bytes, limite: int = LIMITE_PADRAO_BYTES) -> ET.Element:
    """Faz o parse de `dados` devolvendo o elemento raiz.

    Levanta :class:`ArquivoGrandeDemais` acima do limite e :class:`XmlInvalido`
    para conteúdo vazio, com DTD/entidade, ou mal formado.
    """
    if not dados or not dados.strip():
        raise XmlInvalido("conteúdo vazio: nenhum XML para ler")
    if len(dados) > limite:
        raise ArquivoGrandeDemais(
            f"arquivo tem {len(dados)} bytes, acima do limite de {limite} bytes"
        )
    for marca in _MARCAS_PROIBIDAS:
        if marca in dados:
            raise XmlInvalido(
                "documento declara DTD ou ENTIDADE; XML fiscal não precisa disso e "
                "o notasbr recusa o arquivo por segurança"
            )
    try:
        return ET.fromstring(dados)
    except ET.ParseError as exc:
        raise XmlInvalido(f"XML mal formado: {exc}") from exc


# --------------------------------------------------------------------------
# Namespace / nomes locais
# --------------------------------------------------------------------------
def local(tag: object) -> str:
    """Nome local da tag, sem namespace. Comentários e PIs viram string vazia."""
    if not isinstance(tag, str):
        return ""
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[1]
    return tag


def namespace(tag: object) -> str | None:
    """URI de namespace da tag, ou ``None`` se não houver."""
    if isinstance(tag, str) and tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return None


# --------------------------------------------------------------------------
# Navegação
# --------------------------------------------------------------------------
def filhos(elem: ET.Element | None, nome: str) -> list[ET.Element]:
    """Filhos diretos com o nome local informado."""
    if elem is None:
        return []
    return [c for c in elem if local(c.tag) == nome]


def primeiro(elem: ET.Element | None, nome: str) -> ET.Element | None:
    """Primeiro filho direto com o nome local informado."""
    if elem is None:
        return None
    for c in elem:
        if local(c.tag) == nome:
            return c
    return None


def navegar(elem: ET.Element | None, caminho: str) -> ET.Element | None:
    """Navega por um caminho de nomes locais separado por ``/``, sem índice.

    ``navegar(raiz, "NFe/infNFe/ide")`` devolve o primeiro ``ide`` encontrado em
    cada nível. Construa caminhos com nomes únicos por nível — para elementos
    repetidos (``det``), use :func:`filhos`.
    """
    atual = elem
    for parte in caminho.strip("/").split("/"):
        if not parte:
            continue
        atual = primeiro(atual, parte)
        if atual is None:
            return None
    return atual


def texto(elem: ET.Element | None) -> str | None:
    """Texto do elemento sem espaços nas pontas, ou ``None`` se vazio/ausente."""
    if elem is None or elem.text is None:
        return None
    valor = _ESPACOS.sub(" ", elem.text).strip()
    return valor or None


def texto_em(elem: ET.Element | None, caminho: str) -> str | None:
    """Atalho para :func:`texto` + :func:`navegar`."""
    return texto(navegar(elem, caminho))


# --------------------------------------------------------------------------
# Números
# --------------------------------------------------------------------------
def decimal(valor: object) -> Decimal | None:
    """Converte texto fiscal em ``Decimal``.

    Aceita ``"1234.56"`` (padrão do XML) e tolera ``"1234,56"`` de origem
    duvidosa. Devolve ``None`` para vazio ou não numérico — quem chama decide a
    severidade.
    """
    if valor is None:
        return None
    bruto = str(valor).strip()
    if not bruto:
        return None
    normalizado = bruto.replace(" ", "")
    if "," in normalizado:
        normalizado = normalizado.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalizado)
    except InvalidOperation:
        return None


def dinheiro(valor: Decimal | None) -> str | None:
    """Formata um ``Decimal`` com 2 casas, ou ``None``."""
    if valor is None:
        return None
    return str(valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# --------------------------------------------------------------------------
# Localização no documento (para relatório)
# --------------------------------------------------------------------------
def mapa_de_pais(raiz: ET.Element) -> dict[int, ET.Element]:
    """Mapa ``id(elemento) -> pai`` para reconstruir o caminho de um nó."""
    mapa: dict[int, ET.Element] = {}
    for pai in raiz.iter():
        for filho in pai:
            mapa[id(filho)] = pai
    return mapa


def caminho_de(
    raiz: ET.Element,
    alvo: ET.Element,
    pais: dict[int, ET.Element],
) -> str:
    """Caminho legível do `alvo` dentro de `raiz`, com posição entre irmãos repetidos.

    Exemplo: ``NFe/infNFe/det[2]/prod/vProd``.
    """
    partes: list[str] = []
    atual: ET.Element = alvo
    while atual is not raiz:
        pai = pais.get(id(atual))
        if pai is None:  # o elemento não pertence a esta árvore
            break
        nome = local(atual.tag) or "?"
        irmaos = filhos(pai, nome)
        partes.append(f"{nome}[{irmaos.index(atual) + 1}]" if len(irmaos) > 1 else nome)
        atual = pai
    partes.append(local(raiz.tag) or "?")
    return "/".join(reversed(partes))
