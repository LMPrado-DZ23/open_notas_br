"""Erros da SEFIN Nacional normalizados.

A API responde erro em formatos variados (`erros`, `erro`, lista solta, chaves em
maiúscula ou minúscula). Tudo é convertido para `MensagemSefin`, porque quem chama
precisa do **código** (ex.: `E0312`) e não de uma string para dar `split`.

A distinção que mais importa está em `TipoErroFiscal`:

- `REJEICAO` — a SEFIN analisou e recusou. Reenviar igual não resolve.
- `INDISPONIVEL` — não foi processado. Pode reenviar.
- `AMBIGUO` — a conexão caiu depois do envio. **A nota pode existir.** Antes de
  reenviar, é obrigatório consultar a DPS pela chave; senão a retentativa gera
  documento duplicado.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TipoErroFiscal(StrEnum):
    VALIDACAO_LOCAL = "validacao_local"
    REJEICAO = "rejeicao"
    AUTENTICACAO = "autenticacao"
    INDISPONIVEL = "indisponivel"
    AMBIGUO = "ambiguo"
    RESPOSTA_INVALIDA = "resposta_invalida"


@dataclass(slots=True)
class MensagemSefin:
    """Uma mensagem de erro ou alerta devolvida pela SEFIN."""

    codigo: str | None
    descricao: str
    complemento: str | None = None

    def texto(self) -> str:
        prefixo = f"[{self.codigo}] " if self.codigo else ""
        sufixo = f" — {self.complemento}" if self.complemento else ""
        return f"{prefixo}{self.descricao}{sufixo}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "codigo": self.codigo,
            "descricao": self.descricao,
            "complemento": self.complemento,
        }


#: A Produção Restrita mantém cadastro de contribuintes próprio, que muitas
#: prefeituras não atualizam. Recusas sobre o cadastro do prestador podem não
#: ocorrer em produção. Repassar isso ao usuário evita caçar defeito inexistente.
AVISO_HOMOLOGACAO = (
    "Esta recusa veio da homologação (Produção Restrita), que usa um cadastro de "
    "contribuintes próprio, frequentemente desatualizado. Recusas sobre inscrição "
    "municipal, estabelecimento ou situação do CNPJ podem não acontecer em produção. "
    "Recusas sobre dados da nota (serviço, valores, tomador) ocorrem nos dois ambientes."
)

_CODIGOS_CADASTRAIS = frozenset({"E0120", "E0084", "E0010", "E0312"})


@dataclass(eq=False)
class ErroSefin(Exception):
    """Erro de comunicação ou de recusa da SEFIN."""

    tipo: TipoErroFiscal
    resumo: str
    mensagens: list[MensagemSefin] = field(default_factory=list)
    http_status: int | None = None
    corpo: str | None = None
    ambiente: str | None = None  # "1" produção, "2" homologação

    def __post_init__(self) -> None:
        super().__init__(self.resumo)

    def __str__(self) -> str:
        detalhes = "; ".join(m.texto() for m in self.mensagens)
        return f"{self.resumo}: {detalhes}" if detalhes else self.resumo

    @property
    def pode_ter_sido_processada(self) -> bool:
        """True quando reenviar sem consultar pode duplicar documento."""
        return self.tipo is TipoErroFiscal.AMBIGUO

    @property
    def transitorio(self) -> bool:
        return self.tipo in (TipoErroFiscal.INDISPONIVEL, TipoErroFiscal.AMBIGUO)

    @property
    def indica_duplicidade(self) -> bool:
        texto = " ".join(m.texto().lower() for m in self.mensagens)
        return any(
            chave in texto for chave in ("já existe", "ja existe", "duplic", "já foi", "ja foi")
        )

    @property
    def codigos(self) -> list[str]:
        return [m.codigo for m in self.mensagens if m.codigo]

    def as_dict(self) -> dict[str, Any]:
        dados: dict[str, Any] = {
            "tipo": self.tipo.value,
            "resumo": self.resumo,
            "http_status": self.http_status,
            "mensagens": [m.as_dict() for m in self.mensagens],
            "pode_ter_sido_processada": self.pode_ter_sido_processada,
            "transitorio": self.transitorio,
        }
        if self.ambiente == "2" and _CODIGOS_CADASTRAIS & set(self.codigos):
            dados["aviso_homologacao"] = AVISO_HOMOLOGACAO
        return dados


#: Limite de tamanho de uma mensagem. Resposta de erro de servidor web pode vir
#: como página HTML inteira: sem limite, isso entra no banco, no log e no webhook.
LIMITE_MENSAGEM = 300


def _resumir(texto: str) -> str:
    """Colapsa espaços e trunca, marcando o corte.

    Uma página de erro HTML de 3 KB não é "mensagem da SEFIN": é ruído que
    esconde o código real e polui o registro do documento.
    """
    limpo = " ".join(texto.split())
    if limpo.startswith("<"):
        return "resposta HTML do servidor (sem mensagem estruturada)"
    if len(limpo) <= LIMITE_MENSAGEM:
        return limpo
    return limpo[:LIMITE_MENSAGEM].rstrip() + "…"


def _achatar(valor: Any) -> str | None:
    """Texto de um valor que pode vir como str, número, dict ou lista."""
    if valor is None:
        return None
    if isinstance(valor, str):
        return _resumir(valor) or None
    if isinstance(valor, (int, float)):
        return str(valor)
    if isinstance(valor, dict):
        for chave in ("descricao", "mensagem", "message", "detail", "texto"):
            if chave in valor:
                return _achatar(valor[chave])
        return json.dumps(valor, ensure_ascii=False)
    if isinstance(valor, list):
        partes = [p for p in (_achatar(v) for v in valor) if p]
        return "; ".join(partes) or None
    return str(valor)


def _uma_mensagem(item: Any) -> MensagemSefin | None:
    if isinstance(item, str):
        texto = item.strip()
        return MensagemSefin(None, texto) if texto else None
    if not isinstance(item, dict):
        texto = _achatar(item)
        return MensagemSefin(None, texto) if texto else None

    minusculo = {str(k).lower(): v for k, v in item.items()}
    codigo = _achatar(
        minusculo.get("codigo")
        or minusculo.get("code")
        or minusculo.get("cstat")
        or minusculo.get("id")
    )
    descricao = _achatar(
        minusculo.get("descricao")
        or minusculo.get("mensagem")
        or minusculo.get("message")
        or minusculo.get("detail")
        or minusculo.get("texto")
        or minusculo.get("razao")
    )
    complemento = _achatar(
        minusculo.get("complemento") or minusculo.get("correcao") or minusculo.get("dica")
    )
    if descricao is None and codigo is None:
        return None
    return MensagemSefin(codigo, descricao or "(sem descrição)", complemento)


def extrair_mensagens(payload: Any) -> list[MensagemSefin]:
    """Extrai mensagens de qualquer formato conhecido de resposta.

    Ordem de tentativa: lista em `erros`/`erro`/`mensagens`, objeto único, string
    solta. Devolve lista vazia se não houver mensagem reconhecível — quem chama
    decide o que fazer com isso.
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        achadas = [_uma_mensagem(item) for item in payload]
        return [m for m in achadas if m is not None]
    if isinstance(payload, str):
        return [MensagemSefin(None, payload.strip())] if payload.strip() else []
    if not isinstance(payload, dict):
        texto = _achatar(payload)
        return [MensagemSefin(None, texto)] if texto else []

    minusculo = {str(k).lower(): v for k, v in payload.items()}
    for chave in ("erros", "erro", "errors", "mensagens", "message"):
        if chave in minusculo and minusculo[chave] is not None:
            valor = minusculo[chave]
            if isinstance(valor, list):
                achadas = [_uma_mensagem(item) for item in valor]
                filtradas = [m for m in achadas if m is not None]
                if filtradas:
                    return filtradas
            elif isinstance(valor, dict):
                mensagem = _uma_mensagem(valor)
                if mensagem is not None:
                    return [mensagem]
            elif isinstance(valor, str) and valor.strip():
                return [MensagemSefin(None, valor.strip())]

    direta = _uma_mensagem(payload)
    return [direta] if direta is not None else []


def extrair_alertas(payload: Any) -> list[MensagemSefin]:
    """Mensagens de alerta (não bloqueiam a emissão)."""
    if not isinstance(payload, dict):
        return []
    minusculo = {str(k).lower(): v for k, v in payload.items()}
    valor = minusculo.get("alertas") or minusculo.get("avisos")
    if isinstance(valor, list):
        achadas = [_uma_mensagem(item) for item in valor]
        return [m for m in achadas if m is not None]
    if isinstance(valor, dict):
        mensagem = _uma_mensagem(valor)
        return [mensagem] if mensagem else []
    return []
