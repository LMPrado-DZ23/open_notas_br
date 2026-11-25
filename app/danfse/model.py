"""Modelo de dados do DANFSe (v2, NT 008/2026).

Os campos seguem o mapeamento da Nota Técnica nº 008 usado pela implementação de
referência (`notaas-danfse/src/types.ts`), na versão que ela declara: **v1.01,
30/06/2026**. O briefing cita v1.02 (14/07/2026); a divergência está registrada em
`docs/REFERENCIAS.md` e o conjunto de campos aqui é o que consigo justificar.

Regra do produto que o modelo respeita: **o XML autorizado prevalece sobre o
PDF**. Todo campo aqui é derivado do XML; nada é calculado a partir de outro
campo do PDF, para que conferência seja possível.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Pessoa:
    """Prestador, tomador, destinatário ou intermediário."""

    documento: str = ""
    nome: str = ""
    inscricao_municipal: str = ""
    telefone: str = ""
    email: str = ""
    municipio_uf: str = ""
    endereco: str = ""
    cep: str = ""
    #: Campos tributários só usados no prestador.
    opcao_simples: str = ""
    regime_simples: str = ""


@dataclass(slots=True)
class TributacaoIssqn:
    """Bloco ISSQN (§5.8)."""

    trib_issqn: str = ""
    local_incidencia: str = ""
    regime_especial: str = ""
    tipo_imunidade: str = ""
    tipo_suspensao: str = ""
    processo_suspensao: str = ""
    beneficio_municipal: str = ""
    total_deducoes: str = ""
    base_calculo: str = ""
    aliquota: str = ""
    retencao: str = ""
    valor: str = ""
    nao_sujeito: bool = False


@dataclass(slots=True)
class TributacaoFederal:
    """Bloco federal exceto CBS (§5.9)."""

    ret_irrf: str = ""
    ret_cp: str = ""
    ret_csll: str = ""
    pis: str = ""
    cofins: str = ""
    ret_pis_cofins: str = ""


@dataclass(slots=True)
class TributacaoIbsCbs:
    """Bloco IBS/CBS (§5.10) — o que a NT 008 v2 acrescenta."""

    cst_class: str = ""
    indicador_operacao: str = ""
    exclusoes_reducoes_bc: str = ""
    base_calculo: str = ""
    reducao_aliquota: str = ""
    aliquota_ibs_uf: str = ""
    aliquota_ibs_mun: str = ""
    valor_ibs_uf: str = ""
    valor_ibs_mun: str = ""
    total_ibs: str = ""
    aliquota_cbs: str = ""
    valor_cbs: str = ""
    total_ibs_cbs: str = ""

    @property
    def vazio(self) -> bool:
        """True quando não há nada a renderizar (nota sem IBS/CBS)."""
        return not any(
            (
                self.cst_class,
                self.base_calculo,
                self.total_ibs,
                self.valor_cbs,
                self.total_ibs_cbs,
            )
        )


@dataclass(slots=True)
class Totais:
    """Bloco de valor total (§5.11)."""

    valor_servico: str = ""
    desconto_incondicionado: str = ""
    desconto_condicionado: str = ""
    total_retencoes: str = ""
    valor_liquido: str = ""
    total_ibs_cbs: str = ""
    valor_liquido_mais_ibs_cbs: str = ""


@dataclass(slots=True)
class DanfseData:
    """Tudo o que o renderizador precisa. Nada além do XML entra aqui."""

    # Cabeçalho
    municipio: str = ""
    ambiente: str = ""
    chave_acesso: str = ""
    qr_code_url: str = ""

    # Identificação
    numero: str = ""
    competencia: str = ""
    data_processamento: str = ""
    numero_dps: str = ""
    serie_dps: str = ""
    data_emissao_dps: str = ""
    emitente: str = ""
    situacao: str = ""
    finalidade: str = ""

    # Pessoas
    prestador: Pessoa = field(default_factory=Pessoa)
    tomador: Pessoa | None = None
    destinatario: Pessoa | None = None
    intermediario: Pessoa | None = None

    # Serviço
    codigo_tributacao: str = ""
    codigo_nbs: str = ""
    local_prestacao: str = ""
    descricao_servico: str = ""

    # Tributação
    issqn: TributacaoIssqn = field(default_factory=TributacaoIssqn)
    federal: TributacaoFederal = field(default_factory=TributacaoFederal)
    ibscbs: TributacaoIbsCbs = field(default_factory=TributacaoIbsCbs)
    totais: Totais = field(default_factory=Totais)

    #: Campos do XML que não foram encontrados — vira aviso no PDF e no relatório.
    ausentes: list[str] = field(default_factory=list)

    #: Versão do layout declarada pelo documento.
    versao_layout: str = ""

    def tem_ibscbs(self) -> bool:
        return not self.ibscbs.vazio
