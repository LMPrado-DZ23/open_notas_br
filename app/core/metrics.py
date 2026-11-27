"""Métricas no formato de exposição do Prometheus, sem dependência nova.

Por que à mão e não `prometheus-client`: o projeto teria de adicionar dependência nova (regra 11)
para expor **quatro** métricas. O formato de texto é estável e pequeno
(`# HELP` / `# TYPE` / `amostra valor`), e o ADR 0002 já fixou o critério: só entra dependência
quando o custo de não ter supera o de manter.

Decisões que os testes fixam:

- **Rótulo de rota é o *template* (`/v1/emissoes/{invoice_id}`), nunca o caminho cru.** Um label
  por UUID é a definição de cardinalidade explosiva: cresce sem limite e derruba o scraper.
- **Nenhum rótulo de tenant.** Além da cardinalidade, tenant em métrica é dado de cliente exposto
  num endpoint de infraestrutura.
- **O próprio `/metrics` não é contado** — senão o scrape polui a série.
- Estatística de latência é histograma de **faixas fixas**: p95 sai daí sem guardar cada amostra.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field

#: Faixas do histograma de duração, em segundos. Fixas: bucket é contrato, não configuração
#: por requisição. Cobrem o alvo de 300 ms em mock com folga para a cauda.
FAIXAS_SEGUNDOS: tuple[float, ...] = (0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 5.0)

#: Rota usada quando não há template (404, erro antes do roteamento).
ROTA_DESCONHECIDA = "desconhecida"


@dataclass(slots=True)
class _Serie:
    """Contador + histograma de uma combinação de rótulos."""

    total: int = 0
    soma_segundos: float = 0.0
    por_faixa: list[int] = field(default_factory=lambda: [0] * len(FAIXAS_SEGUNDOS))

    def observar(self, segundos: float) -> None:
        self.total += 1
        self.soma_segundos += segundos
        for indice, limite in enumerate(FAIXAS_SEGUNDOS):
            if segundos <= limite:
                self.por_faixa[indice] += 1


class Registro:
    """Registro em memória, protegido por lock.

    Em memória e por processo, como o registro de circuitos (§47): com N instâncias, cada uma
    expõe a própria série e o Prometheus soma na consulta. Não é estado de negócio.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._series: dict[tuple[str, str, str], _Serie] = defaultdict(_Serie)

    def observar(self, *, metodo: str, rota: str, status: int, segundos: float) -> None:
        chave = (metodo.upper(), rota or ROTA_DESCONHECIDA, str(status))
        with self._lock:
            self._series[chave].observar(segundos)

    def limpar(self) -> None:
        """Zera tudo. Existe para isolamento entre testes."""
        with self._lock:
            self._series.clear()

    def series(self) -> dict[tuple[str, str, str], _Serie]:
        with self._lock:
            return {
                chave: _Serie(s.total, s.soma_segundos, list(s.por_faixa))
                for chave, s in self._series.items()
            }

    def renderizar(self) -> str:
        """Formato de exposição do Prometheus (text/plain; version=0.0.4)."""
        linhas: list[str] = []

        linhas.append("# HELP opennotas_http_requisicoes_total Requisições HTTP por rota e status.")
        linhas.append("# TYPE opennotas_http_requisicoes_total counter")
        linhas.append("# HELP opennotas_http_duracao_segundos Duração das requisições HTTP.")
        linhas.append("# TYPE opennotas_http_duracao_segundos histogram")

        for (metodo, rota, status), serie in sorted(self.series().items()):
            rotulos = f'metodo="{metodo}",rota="{rota}",status="{status}"'
            linhas.append(f"opennotas_http_requisicoes_total{{{rotulos}}} {serie.total}")

        for (metodo, rota, status), serie in sorted(self.series().items()):
            rotulos = f'metodo="{metodo}",rota="{rota}",status="{status}"'
            acumulado = 0
            for indice, limite in enumerate(FAIXAS_SEGUNDOS):
                acumulado += serie.por_faixa[indice]
                linhas.append(
                    f'opennotas_http_duracao_segundos_bucket{{{rotulos},le="{limite:g}"}} {acumulado}'
                )
            linhas.append(
                f'opennotas_http_duracao_segundos_bucket{{{rotulos},le="+Inf"}} {serie.total}'
            )
            linhas.append(
                f"opennotas_http_duracao_segundos_sum{{{rotulos}}} {serie.soma_segundos:.6f}"
            )
            linhas.append(f"opennotas_http_duracao_segundos_count{{{rotulos}}} {serie.total}")

        return "\n".join(linhas) + "\n"


#: Registro único do processo.
registro = Registro()
