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
#: Provedores **sem** motor. Hoje vazio: todos os 17 do cadastro têm motor. Mantido para
#: que um provedor novo entre como pendente explícito, e não como surpresa em runtime.
_ENGINE = "motor SOAP pronto em app/nfse/drivers_abrasf.py; falta confirmar "
PENDENTES_LEGADO: dict[str, str] = {
    "abrasf_1_0": _ENGINE + "endpoint e XSD da versão 1.0 do município",
    "abrasf_2_01": _ENGINE + "endpoint e XSD da versão 2.01",
    "abrasf_2_02": _ENGINE + "endpoint e XSD da versão 2.02",
    "abrasf_2_03": _ENGINE + "endpoint e XSD da versão 2.03",
    "abrasf_2_04": _ENGINE + "endpoint da 2.04 (exige assinatura seletiva)",
    "abrasf_2_06": _ENGINE + "endpoint e XSD da versão 2.06",
    "goiania": _ENGINE + "URL e manual do provedor de Goiânia",
    "ginfes": _ENGINE + "URL por município e encoding ISO-8859-1 no provedor",
    "issnet": _ENGINE + "URL e manual do ISSNet",
    "betha": _ENGINE + "URL e manual do Betha",
    "webiss": _ENGINE + "URL e manual do WebISS",
    "simpliss": _ENGINE + "URL e manual do SimplISS",
    "dsf": _ENGINE + "URL e manual do DSF",
    "proddata": _ENGINE + "URL e manual do PRODATA",
    "centri": _ENGINE + "URL e manual do CENTRI",
    "fisco_simplex": _ENGINE + "URL e manual do Fisco Simplex",
}


#: Provedores com **motor** implementado. Não significa "pronto para emitir": o motor ainda
#: precisa da configuração do município (URL, namespace, encoding) vinda do cadastro.
MOTOR_ABRASF = frozenset(
    {
        "abrasf_1_0",
        "abrasf_2_01",
        "abrasf_2_02",
        "abrasf_2_03",
        "abrasf_2_04",
        "abrasf_2_06",
        "ginfes",
        "issnet",
        "betha",
        "webiss",
        "simpliss",
        "dsf",
        "proddata",
        "centri",
        "fisco_simplex",
        "goiania",
    }
)

#: Provedores do cadastro que têm motor utilizável (com configuração).
COM_MOTOR = MOTOR_ABRASF | {"nacional_rest"}


def provedor_suportado(provedor: str) -> bool:
    """Existe motor para este provedor?

    Ser `True` **não** significa que emite: o motor ABRASF exige configuração do município
    (URL com fonte, namespace, encoding). Quem verifica isso é
    `app.nfse.drivers_factory.criar_driver`.
    """
    return provedor in COM_MOTOR


def exigir_implementacao(provedor: str) -> None:
    """Levanta com motivo factual quando o provedor não tem driver utilizável."""
    if provedor_suportado(provedor):
        return
    motivo = PENDENTES_LEGADO.get(
        provedor,
        "provedor desconhecido; nenhum motor implementado e nenhuma fonte registrada",
    )
    raise ErroDeDriver(provedor, motivo)


def capacidade(provedor: str) -> dict[str, bool]:
    """Matriz provedor x capacidade.

    `nacional_rest` está pronto ponta a ponta. Os demais têm motor mas dependem da
    configuração do município — por isso aparecem como `False` em emissão: prometer `True`
    aqui faria a API dizer "posso emitir" para um município sem URL cadastrada.
    """
    suportado = provedor == "nacional_rest"
    return {
        "emitir": suportado,
        "consultar_lote": suportado,
        "consultar_por_rps": suportado,
        "cancelar": suportado,
        "consultar_tomadas": suportado,
        "testar_conectividade": suportado,
    }
