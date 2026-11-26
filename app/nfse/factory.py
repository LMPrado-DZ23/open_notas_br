"""Escolha do adapter NFS-e: dublê quando configurado, real quando não.

Existe para não repetir a decisão em três módulos (lote, integrações, worker) — repetição que já
produziu um defeito real: cada cópia montava `SefinNacionalClient(settings)` e passava `Settings`
no parâmetro `ambiente`, que espera `AmbienteFiscal`. Como `sefin_url()` decide por
`ambiente is AmbienteFiscal.PRODUCAO`, qualquer outra coisa cai em **homologação**, sem erro.

O cliente real precisa de duas coisas que só o serviço de emissão conhece: o `AmbienteFiscal` do
tenant (`TenantFiscalConfig.ambiente`) e o certificado A1 dele. Por isso esta fábrica devolve
`None` no caminho real — `None` significa "o serviço monta o cliente", com os dados do tenant.
"""

from __future__ import annotations

from app.core.config import Settings
from app.nfse.adapter import SefinAdapter, SefinMockAdapter


def montar_adapter(settings: Settings) -> SefinAdapter | None:
    """Dublê apenas quando `NFSE_ADAPTER=mock`; caso contrário, `None`.

    Nunca devolve cliente real: quem monta o cliente real é
    `app.nfse.servico.emitir`, que tem ambiente do tenant e certificado em mãos.
    """
    if settings.nfse_adapter == "mock":
        return SefinMockAdapter()
    return None
