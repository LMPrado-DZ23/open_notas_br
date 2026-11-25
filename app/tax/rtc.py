"""Cálculo de IBS/CBS para NFS-e — regime regular.

Fonte das regras: calculadora oficial da Receita
(`calculadora-rtc-regime-regular`, pacote `br.gov.serpro.rtc`), analisada em
`docs/REFERENCIAS.md`. Diferente do resto do documento, aqui a fonte é o **código
da própria calculadora**, incluindo o SQL que popula as tabelas.

[CONFIRMADO] no esquema de entrada (`NfseBaseCalculoInput`):

- base = ``valorServico - descontoIncondicional - vCalcReeRepRes
  - vCalcDedRedIBSCBS - iss - pis - cofins``
- ``anoFatoGerador`` é obrigatório: a alíquota depende do ano.
- MEI: "bases de cálculo não aplicáveis" (E1302).
- Base negativa é erro (`BASE-NEGATIVA`).
- Optante com opção pendente: cálculo com ressalva.

[CONFIRMADO] na tabela `ALIQUOTA_REFERENCIA` (seed do SQL da calculadora),
com `TRIBUTO`: id 2 = CBS, id 3 = IBS UF, id 4 = IBS Município:

| Vigência | CBS | IBS UF | IBS Mun |
|---|---|---|---|
| 2026-01-01 a 2026-12-31 | 0,90% | 0,10% | 0,00% |
| 2027-01-01 a 2027-12-31 | 8,40% | 0,05% | 0,05% |

Isso resolve a repartição de IBS que antes estava [A VALIDAR]: em 2026 o IBS é
**0,10% integralmente estadual**; em 2027 vira 0,05% UF + 0,05% município.
Os valores do SQL estão em pontos percentuais (0.90 = 0,90%); aqui são
convertidos para fração (0,009).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")

#: Converte ponto percentual do SQL oficial para fração usada no cálculo.
_PCT = Decimal("0.01")


class ErroCalculoTributario(Exception):
    """Entrada inválida para cálculo."""


def _q(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class AliquotaReferencia:
    """Alíquotas de referência de um ano, com a fonte declarada.

    `cbs`, `ibs_uf` e `ibs_mun` são **frações** (0,009 = 0,9%).
    """

    ano: int
    cbs: Decimal
    ibs_uf: Decimal
    ibs_mun: Decimal
    fonte: str = "ALIQUOTA_REFERENCIA — calculadora RTC oficial"

    @property
    def ibs(self) -> Decimal:
        """IBS consolidado do ano (UF + município)."""
        return self.ibs_uf + self.ibs_mun


#: Tabela de referência extraída da calculadora oficial.
#: Não é constante de cálculo: é dado versionado por vigência. Quando a Receita
#: publicar novo ano, acrescentar aqui é a única mudança necessária.
TABELA_ALIQUOTAS: dict[int, AliquotaReferencia] = {
    2026: AliquotaReferencia(
        ano=2026,
        cbs=Decimal("0.90") * _PCT,
        ibs_uf=Decimal("0.10") * _PCT,
        ibs_mun=Decimal("0.00") * _PCT,
    ),
    2027: AliquotaReferencia(
        ano=2027,
        cbs=Decimal("8.40") * _PCT,
        ibs_uf=Decimal("0.05") * _PCT,
        ibs_mun=Decimal("0.05") * _PCT,
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
    """Resultado do cálculo, com a repartição do IBS quando conhecida."""

    base_calculo: Decimal
    aliquota_cbs: Decimal
    aliquota_ibs: Decimal
    valor_cbs: Decimal
    valor_ibs: Decimal
    valor_total: Decimal
    ano_fato_gerador: int
    fonte_aliquota: str
    #: Preenchidos quando a alíquota vem da tabela (que tem a repartição).
    valor_ibs_uf: Decimal | None = None
    valor_ibs_mun: Decimal | None = None
    aliquota_ibs_uf: Decimal | None = None
    aliquota_ibs_mun: Decimal | None = None
    avisos: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return not self.erros

    def to_dict(self) -> dict[str, object]:
        dados: dict[str, object] = {
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
        if self.valor_ibs_uf is not None:
            dados["valor_ibs_uf"] = str(self.valor_ibs_uf)
        if self.valor_ibs_mun is not None:
            dados["valor_ibs_mun"] = str(self.valor_ibs_mun)
        if self.aliquota_ibs_uf is not None:
            dados["aliquota_ibs_uf"] = str(self.aliquota_ibs_uf)
        if self.aliquota_ibs_mun is not None:
            dados["aliquota_ibs_mun"] = str(self.aliquota_ibs_mun)
        return dados


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

    Com a tabela, o IBS sai **repartido** entre UF e município — que é como a
    calculadora oficial guarda e como a SEFIN devolve no XML.
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
    valor_base = _q(valor_base)

    referencia = aliquotas_do_ano(ano_fato_gerador)
    valor_ibs_uf: Decimal | None = None
    valor_ibs_mun: Decimal | None = None
    aliquota_ibs_uf: Decimal | None = None
    aliquota_ibs_mun: Decimal | None = None

    if aliquota_cbs is not None or aliquota_ibs is not None:
        # Exigir as duas é deliberado. Misturar "minha alíquota" com "a tabela
        # do sistema" produz um número que ninguém consegue explicar depois, e
        # quem informa alíquota própria normalmente está contestando a tabela.
        if aliquota_cbs is None or aliquota_ibs is None:
            raise ErroCalculoTributario(
                "informe as duas alíquotas (CBS e IBS) ou nenhuma, para usar a tabela do ano"
            )
        cbs, ibs = aliquota_cbs, aliquota_ibs
        fonte = "parâmetro explícito"
    elif referencia is not None:
        cbs, ibs = referencia.cbs, referencia.ibs
        aliquota_ibs_uf, aliquota_ibs_mun = referencia.ibs_uf, referencia.ibs_mun
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

    if aliquota_ibs_uf is not None and aliquota_ibs_mun is not None:
        valor_ibs_uf = _q(valor_base * aliquota_ibs_uf)
        valor_ibs_mun = _q(valor_base * aliquota_ibs_mun)

    return ResultadoIbsCbs(
        base_calculo=valor_base,
        aliquota_cbs=cbs,
        aliquota_ibs=ibs,
        valor_cbs=valor_cbs,
        valor_ibs=valor_ibs,
        valor_total=_q(valor_cbs + valor_ibs),
        ano_fato_gerador=ano_fato_gerador,
        fonte_aliquota=fonte,
        valor_ibs_uf=valor_ibs_uf,
        valor_ibs_mun=valor_ibs_mun,
        aliquota_ibs_uf=aliquota_ibs_uf,
        aliquota_ibs_mun=aliquota_ibs_mun,
        avisos=avisos,
        erros=erros,
    )
