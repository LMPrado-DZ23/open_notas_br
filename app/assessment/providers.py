"""Provedores de guia de arrecadação.

Premissa regulatória do briefing, respeitada aqui: **não existe guia nacional
única para NFS-e**. O que existe:

- **MAN** — Módulo de Apuração Nacional, que gera o **DNA** (Documento Nacional de
  Arrecadação) para o ISS do regime geral;
- **DAS** — usado para ISS do regime geral via MAN até 31/12/2032 (Resolução CGSN
  188/2026);
- **Guia municipal** — quando o município não adere ao padrão nacional.

Por isso o módulo tem provedores plugáveis e **nenhum layout único inventado**.
Cada provedor devolve o que sabe: número, vencimento e identificador de
pagamento. Layout de boleto/DNA real é [A VALIDAR] contra o manual de cada
sistema — por isso os provedores desta fase são determinísticos e marcados como
mock, e o serviço declara isso na resposta.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.db.models.enums import ProvedorGuia


class ErroDeGuia(Exception):
    """Falha ao gerar a guia."""


@dataclass(slots=True)
class DadosApuracao:
    """O que o provedor precisa para emitir a guia."""

    tenant_id: str
    competencia: str  # AAAA-MM
    total_servicos: Decimal
    total_iss: Decimal
    total_tributos: Decimal
    quantidade_documentos: int


@dataclass(slots=True)
class Guia:
    """Guia gerada. Campos variam por provedor — o comum está aqui."""

    provedor: ProvedorGuia
    numero: str
    vencimento: date
    valor: Decimal
    linha_digitavel: str | None = None
    observacao: str | None = None
    dados: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "provedor": self.provedor.value,
            "numero": self.numero,
            "vencimento": self.vencimento.isoformat(),
            "valor": str(self.valor),
            "linha_digitavel": self.linha_digitavel,
            "observacao": self.observacao,
            "dados": self.dados or {},
        }


@runtime_checkable
class ProvedorDeGuia(Protocol):
    """Contrato de um provedor de guia."""

    provedor: ProvedorGuia

    def gerar(self, apuracao: DadosApuracao) -> Guia: ...


def _digitos(semente: str, quantidade: int) -> str:
    """Dígitos determinísticos a partir de uma semente.

    Determinismo é requisito de teste e de reprocessamento: gerar a mesma guia
    duas vezes para a mesma apuração não pode produzir números diferentes.
    """
    resumo = hashlib.sha256(semente.encode("utf-8")).hexdigest()
    digitos = "".join(c for c in resumo if c.isdigit()).ljust(quantidade, "0")
    return digitos[:quantidade]


def _vencimento(competencia: str, dias: int) -> date:
    """Vencimento como dia fixo do mês seguinte à competência."""
    ano, mes = (int(p) for p in competencia.split("-"))
    mes_seguinte = mes + 1
    ano_seguinte = ano
    if mes_seguinte > 12:
        mes_seguinte = 1
        ano_seguinte += 1
    base = date(ano_seguinte, mes_seguinte, 1)
    return base + timedelta(days=dias - 1)


class ProvedorManDna:
    """MAN/DNA — ISS do regime geral apurado no ambiente nacional.

    [A VALIDAR] O MAN é acessado por serviço próprio da Receita, com layout de DNA
    definido em manual. Esta implementação gera identificadores determinísticos e
    **não** substitui a emissão oficial: serve para o fluxo funcionar ponta a
    ponta e para o parceiro integrar antes de a credencial do MAN existir.
    """

    provedor = ProvedorGuia.MAN

    def gerar(self, apuracao: DadosApuracao) -> Guia:
        if apuracao.total_iss <= 0:
            raise ErroDeGuia(
                "não há ISS apurado na competência: MAN/DNA só gera guia com valor positivo"
            )
        numero = f"DNA{apuracao.competencia.replace('-', '')}{_digitos(apuracao.tenant_id + apuracao.competencia, 6)}"
        return Guia(
            provedor=self.provedor,
            numero=numero,
            vencimento=_vencimento(apuracao.competencia, 20),
            valor=apuracao.total_iss,
            linha_digitavel=_digitos(numero, 48),
            observacao=(
                "guia simulada: o MAN/DNA oficial exige credenciamento próprio e "
                "layout definido em manual [A VALIDAR]"
            ),
            dados={
                "tipo": "DNA",
                "competencia": apuracao.competencia,
                "documentos": apuracao.quantidade_documentos,
            },
        )


class ProvedorDas:
    """DAS — guia do Simples Nacional.

    O DAS cobre tributos do Simples, não só ISS. Usá-lo apenas para ISS depende da
    regra do MAN (Resolução CGSN 188/2026). O provedor declara essa restrição em
    vez de silenciá-la.
    """

    provedor = ProvedorGuia.DAS

    def gerar(self, apuracao: DadosApuracao) -> Guia:
        if apuracao.total_tributos <= 0:
            raise ErroDeGuia("não há tributos apurados na competência para gerar DAS")
        numero = f"DAS{apuracao.competencia.replace('-', '')}{_digitos(apuracao.tenant_id, 6)}"
        return Guia(
            provedor=self.provedor,
            numero=numero,
            vencimento=_vencimento(apuracao.competencia, 20),
            valor=apuracao.total_tributos,
            linha_digitavel=_digitos(numero + "das", 48),
            observacao=(
                "guia simulada: o DAS oficial é gerado no portal do Simples Nacional; "
                "o uso para ISS do regime geral via MAN é permitido até 31/12/2032"
            ),
            dados={"tipo": "DAS", "competencia": apuracao.competencia},
        )


class ProvedorGuiaMunicipal:
    """Guia municipal — para município que não adere ao padrão nacional.

    [A VALIDAR] Cada município tem o seu layout e o seu serviço. Sem a
    especificação do município alvo, o provedor **se recusa** a gerar em vez de
    inventar formato.
    """

    provedor = ProvedorGuia.MUNICIPAL

    def gerar(self, apuracao: DadosApuracao) -> Guia:
        raise ErroDeGuia(
            "guia municipal exige o layout e o serviço da prefeitura do município "
            "emissor; nenhum município está configurado para este provedor. "
            "Use MAN/DNA ou DAS, ou acrescente o provedor do município."
        )


PROVEDORES: dict[ProvedorGuia, ProvedorDeGuia] = {
    ProvedorGuia.MAN: ProvedorManDna(),
    ProvedorGuia.DAS: ProvedorDas(),
    ProvedorGuia.MUNICIPAL: ProvedorGuiaMunicipal(),
}


def obter_provedor(provedor: ProvedorGuia) -> ProvedorDeGuia:
    """Provedor registrado, ou erro explícito.

    O rótulo usa `getattr` porque um chamador pode passar string em vez do enum
    (por exemplo, vindo de payload não validado). Nesse caso o erro precisa ser de
    domínio — "provedor não registrado" — e não `AttributeError` no meio da
    requisição.
    """
    achado = PROVEDORES.get(provedor)
    if achado is None:
        rotulo = getattr(provedor, "value", provedor)
        raise ErroDeGuia(f"não existe provedor de guia registrado para {rotulo}")
    return achado
