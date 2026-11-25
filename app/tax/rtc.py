"""Cálculo de IBS/CBS para NFS-e — regime regular.

Fonte das regras: esquema de entrada da calculadora oficial
(`br.gov.serpro.rtc.api.model.input.nfse.NfseBaseCalculoInput`), analisado em
`docs/REFERENCIAS.md`. O que está **[CONFIRMADO]** nessa fonte:

- A base é ``valorServico - descontoIncondicional - vCalcReeRepRes
  - vCalcDedRedIBSCBS - iss - pis - cofins``.
- ``anoFatoGerador`` é entrada obrigatória: alíquota **depende do ano**.
- MEI: "bases de cálculo não aplicáveis" (aviso E1302).
- Base negativa é erro (`BASE-NEGATIVA`).
- Optante pendente de opção pelo Simples: cálculo com ressalva.

O que **não** está confirmado: a repartição de IBS entre UF e município. O
briefing fala em IBS 0,1% total; a tabela oficial tem `IBSUF` e `IBSMun`
separados. Por isso o cálculo aceita a alíquota de IBS consolidada **e**
alíquotas explícitas por ente — quem precisa da repartição informa, em vez de o
código adivinhar.

Alíquota nunca é constante escondida: vem de tabela versionada por ano, e a
tabela declara a fonte.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")


class ErroCalculoTributario(Exception):
    """Entrada inválida para cálculo."""


def _q(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class AliquotaReferencia:
    """Alíquotas de referência de um ano, com a fonte declarada."""

    ano: int
    cbs: Decimal
    ibs: Decimal
    fonte: str = "briefing (premissa)"


#: Tabela de referência. **Não** é constante de cálculo: é dado versionado.
#: 2026: CBS 0,9% e IBS 0,1% — premissa do briefing. [A VALIDAR] contra a
#: `ALIQUOTA_REFERENCIA` da calculadora oficial, que tem repartição UF/município.
TABELA_ALIQUOTAS: dict[int, AliquotaReferencia] = {
    2026: AliquotaReferencia(
        ano=2026, cbs=Decimal("0.009"), ibs=Decimal("0.001"), fonte="briefing 2026"
    ),
}


def aliquotas_do_ano(ano: int) -> AliquotaReferencia | None:
    """Alíquotas de referência do ano, ou ``None`` se não houver."""
    return TABELA_ALIQUOTAS.get(ano)


@dataclass(slots=True)
class BaseCalculoNfse:
    """Parcelas que compõem a base tributável de uma NFS-e.

    Nomes espelham o esquema oficial para que a conferência seja direta.
    """

    valor_servico: Decimal
    desconto_incondicional: Decimal = Decimal("0.00")
    #: Reembolso/repasse/ressarcimento já tributado, que não integra a base.
    v_calc_ree_rep_res: Decimal = Decimal("0.00")
    #: Dedução/redução da base em locação de imóveis e serviços médicos.
    v_calc_ded_red_ibscbs: Decimal = Decimal("0.00")
    iss: Decimal = Decimal("0.00")
    pis: Decimal = Decimal("0.00")
    cofins: Decimal = Decimal("0.00")

    def base(self) -> Decimal:
        """Base tributável, conforme a fórmula oficial."""
        return (
            self.valor_servico
            - self.desconto_incondicional
            - self.v_calc_ree_rep_res
            - self.v_calc_ded_red_ibscbs
            - self.iss
            - self.pis
            - self.cofins
        )


@dataclass(slots=True)
class ResultadoIbsCbs:
    """Resultado do cálculo, com o que foi usado e o que ficou em ressalva."""

    base_calculo: Decimal
    aliquota_cbs: Decimal
    aliquota_ibs: Decimal
    valor_cbs: Decimal
    valor_ibs: Decimal
    valor_total: Decimal
    ano_fato_gerador: int
    fonte_aliquota: str
    avisos: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return not self.erros

    def to_dict(self) -> dict[str, object]:
        return {
            "base_calculo": str(_q(self.base_calculo)),
            "ano_fato_gerador": self.ano_fato_gerador,
            "aliquota_cbs": str(self.aliquota_cbs),
            "aliquota_ibs": str(self.aliquota_ibs),
            "valor_cbs": str(self.valor_cbs),
            "valor_ibs": str(self.valor_ibs),
            "valor_total": str(self.valor_total),
            "fonte_aliquota": self.fonte_aliquota,
            "avisos": list(self.avisos),
            "erros": list(self.erros),
        }


def calcular_ibscbs(
    base: BaseCalculoNfse,
    *,
    ano_fato_gerador: int,
    aliquota_cbs: Decimal | None = None,
    aliquota_ibs: Decimal | None = None,
    mei: bool = False,
    optante_pendente: bool = False,
) -> ResultadoIbsCbs:
    """Calcula CBS e IBS sobre a base da NFS-e.

    Alíquota resolvida nesta ordem: parâmetro explícito → tabela do ano. Se não
    houver nenhuma das duas, é **erro**: inventar alíquota é o modo mais fácil de
    produzir número fiscal errado com aparência de certo.
    """
    avisos: list[str] = []
    erros: list[str] = []

    valor_servico = base.valor_servico
    if valor_servico <= 0:
        raise ErroCalculoTributario("valor do serviço deve ser maior que zero")

    valor_base = base.base()
    if valor_base < 0:
        erros.append(
            "BASE-NEGATIVA: as deduções e tributos superam o valor do serviço; "
            "a base de cálculo não pode ser negativa"
        )
        valor_base = Decimal("0.00")

    referencia = aliquotas_do_ano(ano_fato_gerador)
    if aliquota_cbs is not None or aliquota_ibs is not None:
        # Exigir as duas é deliberado. Misturar "minha alíquota" com "a tabela
        # do sistema" produz um número que ninguém consegue explicar depois, e
        # quem informa alíquota própria normalmente está justamente contestando
        # a tabela.
        if aliquota_cbs is None or aliquota_ibs is None:
            raise ErroCalculoTributario(
                "informe as duas alíquotas (CBS e IBS) ou nenhuma, para usar a tabela do ano"
            )
        cbs, ibs = aliquota_cbs, aliquota_ibs
        fonte = "parâmetro explícito"
    elif referencia is not None:
        cbs, ibs = referencia.cbs, referencia.ibs
        fonte = referencia.fonte
    else:
        raise ErroCalculoTributario(
            f"não há alíquota de referência para {ano_fato_gerador}; "
            "informe aliquota_cbs e aliquota_ibs explicitamente"
        )

    for nome, aliquota in (("CBS", cbs), ("IBS", ibs)):
        if aliquota < 0 or aliquota > 1:
            raise ErroCalculoTributario(f"alíquota de {nome} fora da faixa 0..1: {aliquota}")

    if mei:
        # A calculadora oficial marca MEI com E1302: bases de cálculo não aplicáveis.
        avisos.append(
            "E1302: operação de MEI — o regime não usa base de cálculo de IBS/CBS; "
            "os valores abaixo são apenas referência e não devem ser recolhidos"
        )
    if optante_pendente:
        avisos.append("optante com opção pelo Simples pendente: cálculo realizado com ressalva")

    valor_cbs = _q(valor_base * cbs)
    valor_ibs = _q(valor_base * ibs)

    return ResultadoIbsCbs(
        base_calculo=_q(valor_base),
        aliquota_cbs=cbs,
        aliquota_ibs=ibs,
        valor_cbs=valor_cbs,
        valor_ibs=valor_ibs,
        valor_total=_q(valor_cbs + valor_ibs),
        ano_fato_gerador=ano_fato_gerador,
        fonte_aliquota=fonte,
        avisos=avisos,
        erros=erros,
    )
