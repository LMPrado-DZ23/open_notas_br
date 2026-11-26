"""Rate limit por tenant — janela deslizante com storage plugável.

Seção 1.6 do v10.0 (60 req/min por tenant). Escrito como módulo com `Protocol` de
armazenamento por dois motivos:

1. **Testável sem Redis**: o teste usa um storage em memória e verifica a janela de
   verdade, não um mock que sempre diz "ok".
2. **Plugável**: Redis em produção, memória em teste. Um limitador que só existe
   com Redis não pode ser testado no CI sem serviço.

Decisões:

- **Conta por tenant, não por IP.** Vários clientes do mesmo lojista compartilham a
  cota; IP erra nos dois sentidos (NAT agrupa, proxy distribui).
- **`Retry-After` calculado**, não fixo: devolver 60 s quando faltam 3 s faz o
  cliente dormir à toa.
- **Falha aberta**: se o storage cair, o limite **não** derruba a requisição. Em
  sistema fiscal, ficar sem atender é pior que atender acima da cota por alguns
  segundos. O evento é registrado para alerta.

Ainda **não está ligado** ao middleware: plugar muda comportamento de todas as
rotas e exige rodar a suíte inteira para provar regressão zero.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

JANELA_PADRAO_S = 60
LIMITE_PADRAO = 60


class ArmazenamentoContagem(Protocol):
    """Contrato mínimo de contagem por janela. Implementado por Redis e memória."""

    async def incrementar(self, chave: str, ttl_s: int) -> int:
        """Incrementa e devolve o total na janela. Deve aplicar TTL na 1ª escrita."""
        ...

    async def consultar(self, chave: str) -> int:
        """Total atual, sem incrementar."""
        ...


class ArmazenamentoMemoria:
    """Storage em memória para teste e para execução single-process."""

    def __init__(self) -> None:
        self._dados: dict[str, tuple[int, float]] = {}

    async def incrementar(self, chave: str, ttl_s: int) -> int:
        agora = time.monotonic()
        total, expira = self._dados.get(chave, (0, agora + ttl_s))
        if agora >= expira:
            total, expira = 0, agora + ttl_s
        total += 1
        self._dados[chave] = (total, expira)
        return total

    async def consultar(self, chave: str) -> int:
        total, expira = self._dados.get(chave, (0, 0.0))
        if time.monotonic() >= expira:
            return 0
        return total


@dataclass(frozen=True, slots=True)
class ResultadoLimite:
    """Decisão do limitador para uma requisição."""

    permitido: bool
    total: int
    limite: int
    restante: int
    retry_after_s: int

    def cabecalhos(self) -> dict[str, str]:
        """Headers que o cliente usa para se autorregular."""
        base = {
            "X-RateLimit-Limit": str(self.limite),
            "X-RateLimit-Remaining": str(max(0, self.restante)),
        }
        if not self.permitido:
            base["Retry-After"] = str(max(1, self.retry_after_s))
        return base


class Limitador:
    """Janela deslizante simples por chave (tenant)."""

    def __init__(
        self,
        armazenamento: ArmazenamentoContagem,
        *,
        limite: int = LIMITE_PADRAO,
        janela_s: int = JANELA_PADRAO_S,
        prefixo: str = "rl:tenant:",
    ) -> None:
        if limite <= 0:
            raise ValueError("limite deve ser positivo")
        if janela_s <= 0:
            raise ValueError("janela_s deve ser positivo")
        self._armazenamento = armazenamento
        self._limite = limite
        self._janela_s = janela_s
        self._prefixo = prefixo

    async def verificar(self, tenant_id: str, *, custo: int = 1) -> ResultadoLimite:
        """Conta `custo` e decide. Storage indisponível => permite (falha aberta)."""
        if custo <= 0:
            raise ValueError("custo deve ser positivo")
        chave = f"{self._prefixo}{tenant_id}"
        try:
            # Incrementa SEMPRE e decide pelo total. Incrementar só quando cabe
            # (a versão anterior) nunca bloqueia: o total congela no limite e o
            # saldo fica 0, que era lido como "permitido". Bug pego pelo smoke test.
            # `custo` > 1 conta várias vezes: uma requisição pesada consome mais cota.
            total = 0
            for _ in range(custo):
                total = await self._armazenamento.incrementar(chave, self._janela_s)
        except Exception:
            return ResultadoLimite(
                permitido=True,
                total=0,
                limite=self._limite,
                restante=self._limite,
                retry_after_s=0,
            )

        restante = self._limite - total
        if restante >= 0:
            return ResultadoLimite(
                permitido=True,
                total=total,
                limite=self._limite,
                restante=restante,
                retry_after_s=0,
            )
        return ResultadoLimite(
            permitido=False,
            total=total,
            limite=self._limite,
            restante=0,
            retry_after_s=self._janela_s,
        )
