"""Drivers de NFS-e: interface comum e roteamento por provedor.

Seção 2.3 do v10.0. Este pacote entrega o **contrato** e o **roteamento**. Só o padrão
nacional tem implementação, porque é o único com leiaute e endpoint confirmados no
repositório.

Os demais provedores existem como **stub que recusa explicitamente** — não como
`NotImplementedError` solto nem como URL inventada. Recusar com motivo é diferente de
fingir: o adaptador chama o provedor certo e recebe "não implementado porque falta X",
em vez de mandar XML para uma URL suposta.

`if municipio == ...` não existe aqui, e não deve existir fora daqui (P9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class CategoriaErro(StrEnum):
    """Espelha o contrato RFC 7807 (§1.4)."""

    SEFAZ = "SEFAZ"
    MUNICIPIO = "MUNICIPIO"
    VALIDACAO = "VALIDACAO"
    INTERNO = "INTERNO"


@dataclass(frozen=True, slots=True)
class ResultadoDriver:
    """Retorno normalizado de qualquer driver. O adaptador não olha o driver."""

    sucesso: bool
    codigo: str | None = None
    mensagem: str | None = None
    xml_enviado: bytes | None = None
    xml_retorno: bytes | None = None
    protocolo: str | None = None
    numero_nfse: str | None = None
    link_nfse: str | None = None
    erro_categoria: CategoriaErro | None = None
    extras: dict[str, Any] = field(default_factory=dict)


class ErroDeDriver(Exception):
    """Provedor existe no cadastro mas não tem implementação utilizável."""

    def __init__(self, provedor: str, motivo: str) -> None:
        super().__init__(f"provedor {provedor} não implementado: {motivo}")
        self.provedor = provedor
        self.motivo = motivo


class BaseNFSeDriver(Protocol):
    """Contrato que todo driver cumpre. Síncrono por natureza fiscal; async no adaptador."""

    nome: str

    async def emitir_rps(self, *, dados: dict[str, Any]) -> ResultadoDriver: ...

    async def consultar_lote(self, *, protocolo: str) -> ResultadoDriver: ...

    async def consultar_nfse_por_rps(self, *, numero_rps: str) -> ResultadoDriver: ...

    async def cancelar_nfse(self, *, numero_nfse: str, motivo: str) -> ResultadoDriver: ...

    async def consultar_nfse_tomadas(self, *, cnpj_tomador: str) -> ResultadoDriver: ...

    async def testar_conectividade(self) -> ResultadoDriver: ...


#: Provedores com contrato definido mas **sem** implementação verificável.
#: O motivo é factual: falta fonte oficial de URL e leiaute por provedor.
PENDENTES: dict[str, str] = {
    "abrasf_1_0": "falta XSD e endpoint oficial da versão 1.0 por município",
    "abrasf_2_01": "falta XSD e endpoint oficial da versão 2.01",
    "abrasf_2_02": "falta XSD e endpoint oficial da versão 2.02",
    "abrasf_2_03": "falta XSD e endpoint oficial da versão 2.03",
    "abrasf_2_04": "falta XSD e endpoint oficial da versão 2.04; exige assinatura seletiva",
    "abrasf_2_06": "falta XSD e endpoint oficial da versão 2.06",
    "goiania": "falta URL e manual do provedor de Goiânia",
    "ginfes": "falta URL por município e confirmação do encoding ISO-8859-1",
    "issnet": "falta URL e manual do provedor ISSNet",
    "betha": "falta URL e manual do provedor Betha",
    "webiss": "falta URL e manual do provedor WebISS",
    "simpliss": "falta URL e manual do provedor SimplISS",
    "dsf": "falta URL e manual do provedor DSF",
    "proddata": "falta URL e manual do provedor PRODATA",
    "centri": "falta URL e manual do provedor CENTRI",
    "fisco_simplex": "falta URL e manual do provedor Fisco Simplex",
}


def provedor_suportado(provedor: str) -> bool:
    """Só o padrão nacional tem implementação hoje."""
    return provedor == "nacional_rest"


def exigir_implementacao(provedor: str) -> None:
    """Levanta com motivo factual quando o provedor não tem driver utilizável."""
    if provedor_suportado(provedor):
        return
    motivo = PENDENTES.get(provedor, "provedor desconhecido; nenhuma fonte oficial registrada")
    raise ErroDeDriver(provedor, motivo)


def capacidade(provedor: str) -> dict[str, bool]:
    """Matriz provedor x capacidade, para `docs/nfse/drivers.md` e para a API."""
    suportado = provedor_suportado(provedor)
    return {
        "emitir": suportado,
        "consultar_lote": suportado,
        "consultar_por_rps": suportado,
        "cancelar": suportado,
        "consultar_tomadas": suportado,
        "testar_conectividade": suportado,
    }
