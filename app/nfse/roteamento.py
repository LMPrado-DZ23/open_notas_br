"""Decisão de rota da NFS-e: nacional ou não, e com que fundamento.

**Por que este módulo existe.** Até 2026-11-27 o campo `aderente_emissor_nacional` era gravado e
**nunca consultado**: nenhuma decisão de emissão olhava para ele (auditoria §77). O sistema sempre
tentava o Emissor Nacional, inclusive para município cujo parâmetro oficial diz o contrário — e o
erro só aparecia como rejeição `E0312` vinda da SEFIN, depois de gerar, assinar e transmitir.

**O que este módulo NÃO faz.** Não inventa regra fiscal. Cada ramo abaixo cita a fonte que o
sustenta, e o que não foi confirmado está marcado como não implementado, não como comportamento.

Fonte usada (consultada em 2026-11-27):

- Portal Nacional da NFS-e — Perguntas Frequentes v1.2 (arquivo de 2026-10-27) e v1.3 (2026-11-06):
  <https://www.gov.br/nfse/pt-br/perguntas-frequentes>
  - ME/EPP optantes do Simples Nacional emitem **exclusivamente** pelo Emissor Nacional a partir de
    **01/11/2026**; sistemas municipais ficam impedidos de autorizar essas emissões;
  - `situacaoEmissaoPadraoContribuintesRFB = 0` significa que o município **não** usa os Emissores
    Nacionais como padrão (a emissão ocorre no sistema próprio da prefeitura);
  - a "Autorização de Uso dos Emissores Públicos" (CNC/Painel do Contribuinte) define por onde
    aquele contribuinte emite, e não é opção paralela: é trava de exclusividade.

**Exceções não implementadas, de propósito:** a alegação de que MEI e operações do grupo 99 escapam
de `aderenteEmissorNacional = 0` **não foi confirmada** em fonte oficial nesta sessão. Não há ramo
para elas aqui. Implementar exceção sem fonte seria pior que bloquear: produziria nota pela rota
errada com aparência de autorizada. Quando a fonte aparecer, o ramo entra com teste próprio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

#: Competência a partir da qual ME/EPP do Simples Nacional são obrigadas ao Emissor Nacional.
#: Fonte: FAQ NFS-e v1.2/v1.3 (gov.br), consultada em 2026-11-27. A regra vale por **competência**
#: da nota, não pela data em que a API foi chamada — nota de competência anterior não é
#: reclassificada retroativamente.
COMPETENCIA_OBRIGATORIA_SIMPLES = date(2026, 11, 1)

Rota = Literal["nacional", "municipal", "indefinida"]


@dataclass(frozen=True, slots=True)
class DecisaoRota:
    """Resultado da decisão, com o motivo legível e o que falta quando bloqueia."""

    rota: Rota
    #: `True` quando a emissão pode seguir pelo Emissor Nacional nesta chamada.
    permitido: bool
    motivo: str
    #: Pré-requisito pendente quando `permitido=False` (nunca vazio nesse caso).
    pendencia: str | None = None
    #: `True` quando a decisão se apoia em parâmetro **confirmado em fonte oficial**.
    confirmado: bool = False


def _competencia(texto: str | None) -> date | None:
    """`AAAA-MM` → primeiro dia do mês. Entrada inválida vira `None` (não inventa data)."""
    if not texto or len(texto) != 7 or texto[4] != "-":
        return None
    try:
        ano, mes = int(texto[:4]), int(texto[5:])
    except ValueError:
        return None
    if not 1 <= mes <= 12:
        return None
    return date(ano, mes, 1)


def decidir_rota(
    *,
    aderente_emissor_nacional: bool,
    aderente_confirmado: bool,
    simples_nacional: bool,
    optante_mei: bool,
    competencia: str | None,
    ambiente: str,
) -> DecisaoRota:
    """Decide se a emissão pode ir pelo Emissor Nacional.

    A ordem dos ramos é deliberada: **obrigação legal vem antes de parâmetro municipal**, porque a
    partir de 01/11/2026 o município não é mais autorizador para ME/EPP do Simples, aderente ou não.

    `ambiente="producao"` exige parâmetro confirmado; fora de produção (homologação/teste) a ausência
    de confirmação vira **aviso**, não bloqueio — senão nenhuma instalação nova conseguiria testar
    antes de parametrizar, e o teste local já roda contra o dublê, não contra a SEFIN.
    """
    competencia_data = _competencia(competencia)
    producao = ambiente == "producao"

    # 1. Obrigação nacional do Simples (ME/EPP, não MEI) a partir da competência de 2026-11.
    #    Fonte: FAQ NFS-e v1.2/v1.3. Vale mesmo com `aderente=False`, porque o município deixou de
    #    poder autorizar essas notas.
    if (
        simples_nacional
        and not optante_mei
        and competencia_data is not None
        and competencia_data >= COMPETENCIA_OBRIGATORIA_SIMPLES
    ):
        return DecisaoRota(
            rota="nacional",
            permitido=True,
            motivo=(
                "ME/EPP do Simples Nacional com competência a partir de 2026-11: emissão "
                "exclusivamente pelo Emissor Nacional (FAQ NFS-e v1.2/v1.3)"
            ),
            confirmado=True,
        )

    # 2. Parâmetro municipal não confirmado: em produção, não emite; fora, avisa e segue.
    if not aderente_confirmado:
        if producao:
            return DecisaoRota(
                rota="indefinida",
                permitido=False,
                motivo=(
                    "o parâmetro `aderenteEmissorNacional` do município não foi conferido em fonte "
                    "oficial; em produção a rota não pode ser presumida"
                ),
                pendencia=(
                    "registrar `aderente_confirmado_em` e `aderente_fonte` na configuração fiscal "
                    "do tenant após consultar o Painel Municipal / parâmetros oficiais"
                ),
                confirmado=False,
            )
        return DecisaoRota(
            rota="nacional",
            permitido=True,
            motivo=(
                "parâmetro municipal não confirmado em fonte oficial; seguir pelo Emissor Nacional "
                "fora de produção, com aviso (não é prova de rota correta em produção)"
            ),
            confirmado=False,
        )

    # 3. Município aderente: Emissor Nacional é o padrão.
    if aderente_emissor_nacional:
        return DecisaoRota(
            rota="nacional",
            permitido=True,
            motivo="município aderente ao Emissor Nacional (parâmetro confirmado)",
            confirmado=True,
        )

    # 4. Município não aderente e contribuinte sem obrigação nacional: a emissão precisa ir pela
    #    integração municipal, que este repositório **não implementa** (§66: sem transporte real).
    return DecisaoRota(
        rota="municipal",
        permitido=False,
        motivo=(
            "município não aderente ao Emissor Nacional (parâmetro confirmado) e contribuinte fora "
            "da obrigação nacional; a emissão precisa ir pela integração municipal"
        ),
        pendencia=(
            "implementar/homologar o transporte municipal (§66) ou obter a Autorização de Uso dos "
            "Emissores Públicos (CNC/Painel do Contribuinte) para este contribuinte"
        ),
        confirmado=True,
    )
