"""Infraestrutura das regras: contexto, registro e utilitários.

Uma regra é uma função que recebe um :class:`Contexto` já preparado e registra
achados. Ela nunca levanta exceção para sinalizar problema no documento — problema
é achado, não exceção. Exceção fica reservada a falha de leitura.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from xml.etree import ElementTree as ET

from ..modelos import Achado, Pulada, Severidade
from ..xml_util import caminho_de, filhos, mapa_de_pais, navegar, texto, texto_em

#: Diferença aceita em comparação de valores monetários (1 centavo).
TOLERANCIA = Decimal("0.01")


@dataclass
class Contexto:
    """Estado compartilhado entre as regras de um documento."""

    raiz: ET.Element
    tipo: str
    corpo: ET.Element
    ns: str | None = None
    versao_layout: str | None = None
    chave: str | None = None
    #: ChaveAcesso decomposta, quando a chave for válida. Não se chama `info`
    #: para não colidir com o método :meth:`info` de registro de achado.
    chave_parseada: Any = None
    arquivo: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)
    achados: list[Achado] = field(default_factory=list)
    puladas: list[Pulada] = field(default_factory=list)
    _pais: dict[int, ET.Element] = field(default_factory=dict, repr=False)
    _prefixo: str = ""

    def __post_init__(self) -> None:
        if not self._pais:
            self._pais = mapa_de_pais(self.raiz)
        if not self._prefixo:
            self._prefixo = caminho_de(self.raiz, self.corpo, self._pais)

    # -- localização --------------------------------------------------
    def caminho(self, relativo: str = "") -> str:
        """Caminho absoluto no XML a partir de um caminho relativo ao corpo."""
        if not relativo:
            return self._prefixo
        return f"{self._prefixo}/{relativo}" if self._prefixo else relativo

    def localizar(self, elemento: ET.Element) -> str:
        """Caminho absoluto de um elemento arbitrário desta árvore."""
        return caminho_de(self.raiz, elemento, self._pais)

    # -- acesso (relativo ao corpo: infNFe / infCte) -------------------
    def elem(self, relativo: str) -> ET.Element | None:
        return navegar(self.corpo, relativo)

    def txt(self, relativo: str) -> str | None:
        return texto_em(self.corpo, relativo)

    # -- acesso pela raiz (para irmãos do corpo: protNFe, Signature) ---
    def elem_raiz(self, caminho: str) -> ET.Element | None:
        """Navega a partir da raiz do documento, não do corpo."""
        return navegar(self.raiz, caminho)

    def txt_raiz(self, caminho: str) -> str | None:
        return texto_em(self.raiz, caminho)

    def dec(self, relativo: str) -> Decimal | None:
        from ..xml_util import decimal as _dec

        return _dec(self.txt(relativo))

    def filhos(self, nome: str) -> list[ET.Element]:
        return filhos(self.corpo, nome)

    def filhos_de(self, elemento: ET.Element | None, nome: str) -> list[ET.Element]:
        return filhos(elemento, nome)

    def txt_de(self, elemento: ET.Element | None, caminho: str) -> str | None:
        return texto_em(elemento, caminho)

    # -- registro -----------------------------------------------------
    def _registrar(
        self,
        codigo: str,
        severidade: Severidade,
        mensagem: str,
        relativo: str,
        detalhe: dict[str, Any],
    ) -> None:
        self.achados.append(
            Achado(
                codigo=codigo,
                severidade=severidade,
                mensagem=mensagem,
                caminho=self.caminho(relativo),
                detalhe=detalhe,
            )
        )

    def erro(self, codigo: str, mensagem: str, relativo: str = "", **detalhe: Any) -> None:
        self._registrar(codigo, Severidade.ERRO, mensagem, relativo, detalhe)

    def aviso(self, codigo: str, mensagem: str, relativo: str = "", **detalhe: Any) -> None:
        self._registrar(codigo, Severidade.AVISO, mensagem, relativo, detalhe)

    def info(self, codigo: str, mensagem: str, relativo: str = "", **detalhe: Any) -> None:
        self._registrar(codigo, Severidade.INFO, mensagem, relativo, detalhe)

    # -- registro em elemento fora do corpo (ex.: Signature, protNFe) --
    def _registrar_em(
        self,
        codigo: str,
        severidade: Severidade,
        mensagem: str,
        elemento: ET.Element | None,
        detalhe: dict[str, Any],
    ) -> None:
        caminho = self.localizar(elemento) if elemento is not None else ""
        self.achados.append(
            Achado(
                codigo=codigo,
                severidade=severidade,
                mensagem=mensagem,
                caminho=caminho,
                detalhe=detalhe,
            )
        )

    def erro_em(
        self, codigo: str, mensagem: str, elemento: ET.Element | None, **detalhe: Any
    ) -> None:
        """Registra erro apontando o caminho real de um elemento (fora do corpo)."""
        self._registrar_em(codigo, Severidade.ERRO, mensagem, elemento, detalhe)

    def aviso_em(
        self, codigo: str, mensagem: str, elemento: ET.Element | None, **detalhe: Any
    ) -> None:
        self._registrar_em(codigo, Severidade.AVISO, mensagem, elemento, detalhe)

    def info_em(
        self, codigo: str, mensagem: str, elemento: ET.Element | None, **detalhe: Any
    ) -> None:
        self._registrar_em(codigo, Severidade.INFO, mensagem, elemento, detalhe)

    def pular(self, codigo: str, motivo: str) -> None:
        """Marca a regra como não avaliada. Não conta como aprovação."""
        self.puladas.append(Pulada(codigo=codigo, motivo=motivo))

    # -- utilidades de valor ------------------------------------------
    def texto_sim_nao(self, relativo: str) -> str | None:
        return self.txt(relativo)


@dataclass(frozen=True, slots=True)
class Regra:
    """Metadados + função de uma regra."""

    codigo: str
    descricao: str
    tipos: tuple[str, ...]
    funcao: Callable[[Contexto], None]

    def aplicavel(self, tipo: str) -> bool:
        return tipo in self.tipos


REGRAS: list[Regra] = []


def regra(
    codigo: str,
    descricao: str,
    tipos: Iterable[str] = ("nfe", "cte"),
) -> Callable[[Callable[[Contexto], None]], Callable[[Contexto], None]]:
    """Decorador que registra uma função como regra do catálogo."""

    def decorador(funcao: Callable[[Contexto], None]) -> Callable[[Contexto], None]:
        if any(r.codigo == codigo for r in REGRAS):
            raise RuntimeError(f"código de regra duplicado: {codigo}")
        REGRAS.append(Regra(codigo, descricao, tuple(tipos), funcao))
        return funcao

    return decorador


def regras_para(tipo: str) -> list[Regra]:
    """Regras aplicáveis ao tipo de documento, na ordem de registro."""
    return [r for r in REGRAS if r.aplicavel(tipo)]


# ----------------------------------------------------------------------
# Helpers usados por mais de uma regra
# ----------------------------------------------------------------------
def diferenca(a: Decimal, b: Decimal) -> Decimal:
    return abs(a - b)


def iguais(a: Decimal, b: Decimal, tolerancia: Decimal = TOLERANCIA) -> bool:
    return diferenca(a, b) <= tolerancia


def exigir_texto(ctx: Contexto, relativo: str) -> str | None:
    """Devolve o texto e registra erro de obrigatoriedade quando ausente.

    O código do achado deriva do caminho para permanecer estável e legível:
    ``ide/nNF`` ausente vira ``OBRIG-ide-nNF``.
    """
    valor = ctx.txt(relativo)
    if valor is None:
        codigo = "OBRIG-" + relativo.replace("/", "-")
        ctx.erro(codigo, f"campo obrigatório ausente ou vazio: {relativo}", relativo)
    return valor


def texto_ou_none(elemento: ET.Element | None, caminho: str) -> str | None:
    valor = texto_em(elemento, caminho)
    return valor if valor else None


__all__ = [
    "REGRAS",
    "TOLERANCIA",
    "Contexto",
    "Regra",
    "diferenca",
    "exigir_texto",
    "filhos",
    "iguais",
    "navegar",
    "regra",
    "regras_para",
    "texto",
    "texto_ou_none",
]
