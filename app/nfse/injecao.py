"""Invocação da emissão sob circuito, sem alterar o `emissao_service`.

O `emissao_service.emitir` continua puro: ele não sabe de circuito. Este módulo é a
camada que **decide** se a chamada pode acontecer, usando o registro compartilhado.

Por que assim, e não editando o serviço:

- o serviço é o caminho mais quente do sistema (200+ testes dependem dele). Trocar a
  chamada dentro dele exige rodar a suíte inteira para provar regressão zero
- aqui a decisão fica testável isoladamente, com dublê do serviço: os testes provam que
  a chave do circuito é a certa e que serviço **não** é chamado com circuito aberto

Trocar a rota para usar esta função é uma linha; o que falta é a verificação completa.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.nfse.resiliencia import RegistroCircuitos, chave_sefaz, executar

#: Operação usada na chave do circuito para autorização de NFS-e.
OPERACAO_EMISSAO = "autorizacao"
#: Operações de escrita na mesma SEFIN. Circuito separado por operação: uma rejeição de
#: cancelamento não deve abrir o circuito de emissão, e vice-versa.
OPERACAO_CANCELAMENTO = "cancelamento"
OPERACAO_EVENTO = "evento"

#: Chave de circuito para o padrão nacional. Não é UF: a NFS-e nacional não depende de
#: SEFAZ estadual, então um único circuito cobre todos os municípios. Vira por município
#: quando existirem drivers municipais.
UF_NACIONAL = "NACIONAL"


async def executar_com_circuito[T](
    registro: RegistroCircuitos,
    *,
    uf: str,
    operacao: str,
    acao: Callable[[], Awaitable[T]],
) -> T:
    """Executa `acao` sob o circuito de `(uf, operacao)`.

    Genérico de propósito: emissão, cancelamento e evento falam com a **mesma** SEFIN e
    sofrem do mesmo modo quando ela está fora. Antes só a emissão tinha circuito; as outras
    duas queimavam timeout próprio a cada requisição.
    """
    return await executar(registro, chave_sefaz(uf, operacao), acao)


async def emitir_com_circuito[T](
    registro: RegistroCircuitos,
    *,
    uf: str,
    acao: Callable[[], Awaitable[T]],
) -> T:
    """Executa a emissão respeitando o circuito da UF.

    `CircuitoAberto` é levantado **antes** de chamar o serviço: quando a SEFAZ da UF está
    fora, insistir queima timeout e atrasa a fila inteira dos outros tenants.

    A chave inclui a UF porque GO cair não pode parar SP.
    """
    return await executar_com_circuito(registro, uf=uf, operacao=OPERACAO_EMISSAO, acao=acao)


def chave_da_emissao(uf: str) -> str:
    """Chave usada para a emissão nesta UF. Exposta para health e teste."""
    return chave_sefaz(uf, OPERACAO_EMISSAO)


def descrever(registro: RegistroCircuitos, *ufs: str) -> dict[str, Any]:
    """Estado dos circuitos de emissão das UFs informadas."""
    return {uf.upper(): registro.estados().get(chave_da_emissao(uf), "inexistente") for uf in ufs}
