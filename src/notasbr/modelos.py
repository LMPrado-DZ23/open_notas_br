"""Modelos do relatório de auditoria.

O objeto `Relatorio` é a saída pública. `to_dict()` produz o contrato JSON
versionado por ``notasbr.relatorio/1``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .versao import SCHEMA_RELATORIO, VERSAO


class Severidade(str, Enum):
    """Gravidade de um achado.

    - ``ERRO``: o documento está inconsistente segundo a regra. Reprova.
    - ``AVISO``: indício de problema ou exigência que não invalida o documento.
    - ``INFORMACAO``: constatação útil para conferência, sem juízo.
    """

    ERRO = "erro"
    AVISO = "aviso"
    INFO = "informacao"


_ORDEM = {Severidade.ERRO: 0, Severidade.AVISO: 1, Severidade.INFO: 2}


@dataclass(slots=True)
class Achado:
    """Um resultado de regra, com o caminho exato do XML."""

    codigo: str
    severidade: Severidade
    mensagem: str
    caminho: str = ""
    detalhe: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        saida: dict[str, Any] = {
            "codigo": self.codigo,
            "severidade": self.severidade.value,
            "mensagem": self.mensagem,
        }
        if self.caminho:
            saida["caminho"] = self.caminho
        if self.detalhe:
            saida["detalhe"] = self.detalhe
        return saida


@dataclass(slots=True)
class Pulada:
    """Regra que não foi avaliada, e por quê.

    Aparecer aqui não é falha: é transparência. Uma regra pulada nunca conta como
    aprovada.
    """

    codigo: str
    motivo: str

    def to_dict(self) -> dict[str, str]:
        return {"codigo": self.codigo, "motivo": self.motivo}


@dataclass(slots=True)
class Resumo:
    """Contadores do relatório."""

    erros: int = 0
    avisos: int = 0
    informacoes: int = 0
    regras_avaliadas: int = 0
    regras_puladas: int = 0

    @property
    def situacao(self) -> str:
        """``reprovado``, ``aprovado_com_avisos`` ou ``aprovado``."""
        if self.erros:
            return "reprovado"
        if self.avisos:
            return "aprovado_com_avisos"
        return "aprovado"

    def to_dict(self) -> dict[str, Any]:
        return {
            "situacao": self.situacao,
            "erros": self.erros,
            "avisos": self.avisos,
            "informacoes": self.informacoes,
            "regras_avaliadas": self.regras_avaliadas,
            "regras_puladas": self.regras_puladas,
        }


@dataclass(slots=True)
class Relatorio:
    """Resultado completo da auditoria de um documento."""

    tipo: str
    raiz: str
    versao_layout: str | None = None
    chave: str | None = None
    arquivo: str | None = None
    sha256: str | None = None
    modelo: str | None = None
    ambiente: str | None = None
    emitente: dict[str, Any] = field(default_factory=dict)
    destinatario: dict[str, Any] = field(default_factory=dict)
    valor_total: str | None = None
    achados: list[Achado] = field(default_factory=list)
    puladas: list[Pulada] = field(default_factory=list)
    limitacoes: list[str] = field(default_factory=list)
    regras_avaliadas: int = 0
    duracao_ms: float = 0.0

    # -- leitura ------------------------------------------------------
    @property
    def resumo(self) -> Resumo:
        erros = sum(1 for a in self.achados if a.severidade is Severidade.ERRO)
        avisos = sum(1 for a in self.achados if a.severidade is Severidade.AVISO)
        infos = sum(1 for a in self.achados if a.severidade is Severidade.INFO)
        return Resumo(
            erros=erros,
            avisos=avisos,
            informacoes=infos,
            regras_avaliadas=self.regras_avaliadas,
            regras_puladas=len(self.puladas),
        )

    @property
    def aprovado(self) -> bool:
        """True quando nenhuma regra produziu ``erro``.

        Aviso não reprova. Use :attr:`Resumo.situacao` para a distinção fina.
        """
        return not any(a.severidade is Severidade.ERRO for a in self.achados)

    def por_severidade(self, severidade: Severidade) -> list[Achado]:
        return [a for a in self.achados if a.severidade is severidade]

    # -- serialização -------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Contrato JSON estável (``notasbr.relatorio/1``)."""
        ordenados = sorted(self.achados, key=lambda a: (_ORDEM[a.severidade], a.codigo))
        return {
            "schema": SCHEMA_RELATORIO,
            "versao_ferramenta": VERSAO,
            "arquivo": self.arquivo,
            "sha256": self.sha256,
            "documento": {
                "tipo": self.tipo,
                "raiz": self.raiz,
                "versao_layout": self.versao_layout,
                "chave": self.chave,
                "modelo": self.modelo,
                "ambiente": self.ambiente,
                "emitente": self.emitente or None,
                "destinatario": self.destinatario or None,
                "valor_total": self.valor_total,
            },
            "resumo": self.resumo.to_dict(),
            "achados": [a.to_dict() for a in ordenados],
            "regras_puladas": [p.to_dict() for p in self.puladas],
            "limitacoes": list(self.limitacoes),
            "duracao_ms": round(self.duracao_ms, 2),
        }
