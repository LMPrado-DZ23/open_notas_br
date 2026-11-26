"""Assinatura XMLDSig do RPS/lote ABRASF.

Reutiliza o assinador do projeto (`app.nfse.signer.assinar`), que já resolve C14N, digest e
prefixo de `Signature`. Duplicar essa lógica seria a segunda oportunidade de errar o mesmo
detalhe.

Diferença em relação à DPS nacional: o leiaute ABRASF assina o **`InfRps`/`InfDeclaracao`**
por `Id`, não o documento inteiro, e o provedor pode querer assinar **só o RPS ou o lote**.
Assinar os dois quando ele espera um produz recusa — por isso a função recebe `alvo`
explícito em vez de adivinhar.

**Sem URL e sem regra fiscal aqui**: só transforma bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from lxml import etree

from app.certificates.cofre import CertificadoA1
from app.nfse.errors import ErroSefin, TipoErroFiscal
from app.nfse.signer import ErroAssinatura, assinar


class AlvoAssinatura(StrEnum):
    """O que o provedor espera assinado. Decide-se pelo manual do provedor."""

    RPS = "rps"
    LOTE = "lote"


#: Tags que carregam o `Id` a ser referenciado, por alvo.
_TAG_DO_ALVO: dict[AlvoAssinatura, tuple[str, ...]] = {
    AlvoAssinatura.RPS: ("InfDeclaracaoPrestacaoServico", "InfRps"),
    AlvoAssinatura.LOTE: ("LoteRps", "InfLoteRps"),
}


@dataclass(frozen=True, slots=True)
class ResultadoAssinatura:
    xml: bytes
    alvo: AlvoAssinatura
    id_assinado: str


def _achar_alvo(raiz: etree._Element, alvo: AlvoAssinatura) -> etree._Element | None:
    """Primeiro elemento, em qualquer profundidade, cuja tag case com o alvo."""
    for localname in _TAG_DO_ALVO[alvo]:
        encontrado = raiz.find(f".//{{*}}{localname}")
        if encontrado is None:
            encontrado = raiz.find(f".//{localname}")
        if encontrado is not None:
            return encontrado
    return None


def assinar_rps(
    xml: bytes,
    certificado: CertificadoA1,
    *,
    alvo: AlvoAssinatura = AlvoAssinatura.RPS,
) -> ResultadoAssinatura:
    """Assina o elemento do alvo e devolve o XML com a `Signature` embutida.

    Falhas são traduzidas para `ErroSefin(INTERNO)`: erro de assinatura é nosso, não do
    município, e classificá-lo como recusa fiscal mandaria o lojista procurar o problema no
    lugar errado.
    """
    try:
        raiz = etree.fromstring(xml)
    except etree.XMLSyntaxError as exc:
        raise ErroSefin(
            TipoErroFiscal.VALIDACAO_LOCAL, f"RPS inválido para assinatura: {exc}"
        ) from exc

    elemento = _achar_alvo(raiz, alvo)
    if elemento is None:
        raise ErroSefin(
            TipoErroFiscal.VALIDACAO_LOCAL,
            f"RPS sem elemento para assinar como '{alvo.value}' "
            f"(esperado um de {_TAG_DO_ALVO[alvo]})",
        )

    identificador = elemento.get("Id")
    if not identificador:
        # Sem `Id` não há `URI` de referência possível: o leiaute exige esse atributo.
        raise ErroSefin(
            TipoErroFiscal.VALIDACAO_LOCAL,
            f"elemento '{etree.QName(elemento).localname}' precisa de atributo Id "
            "para ser assinado",
        )

    try:
        assinado = assinar(raiz, certificado, id_elemento=identificador)
    except ErroAssinatura as exc:
        raise ErroSefin(TipoErroFiscal.VALIDACAO_LOCAL, f"falha ao assinar o RPS: {exc}") from exc

    # `assinar` devolve a árvore; o driver e o transporte trabalham com bytes.
    return ResultadoAssinatura(xml=etree.tostring(assinado), alvo=alvo, id_assinado=identificador)
