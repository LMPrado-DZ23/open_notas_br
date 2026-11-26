"""Fábrica de drivers: do registro do município ao driver configurado.

Fecha o roteamento do v10.0 §2.3: `municipios_nfse.provedor` escolhe o motor, e a
configuração (URL, namespace, SOAP, encoding) vem do próprio registro.

Duas invariantes que os testes cobrem:

- **URL tem de ser https e ter fonte registrada.** Município sem `fonte_url` não vira
  driver: sem fonte, a URL é chute, e chute em serviço fiscal é o que R8 proíbe.
- **Provedor sem motor recusa com motivo factual**, herdado de `exigir_implementacao`.

Nada de rede aqui: a fábrica monta, não chama.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.nfse.drivers import ErroDeDriver, exigir_implementacao
from app.nfse.drivers_abrasf import (
    AbrasfBaseDriver,
    ConfiguracaoAbrasf,
    TransporteProvedor,
    assinador_de,
)

#: Provedores atendidos pelo motor ABRASF parametrizável.
ABRASF = frozenset(
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


@dataclass(frozen=True, slots=True)
class MunicipioParaDriver:
    """O que a fábrica precisa do registro, sem acoplar ao ORM.

    Copiar os campos (em vez de receber a linha) deixa o teste construí-lo sem sessão e
    impede que a fábrica faça consulta escondida.
    """

    codigo_ibge: str
    provedor: str
    url: str | None
    namespace: str
    versao_soap: str = "1.2"
    encoding: str = "UTF-8"
    assina_rps: bool = True
    assina_lote: bool = True
    fonte_url: str | None = None

    def __post_init__(self) -> None:
        if len(self.codigo_ibge) != 7 or not self.codigo_ibge.isdigit():
            raise ValueError(f"código IBGE inválido: {self.codigo_ibge!r}")


def criar_driver(
    municipio: MunicipioParaDriver,
    *,
    transporte: TransporteProvedor,
    certificado: Any | None = None,
    alvo_assinatura: str = "rps",
) -> AbrasfBaseDriver:
    """Monta o driver do município. Não faz rede."""
    exigir_implementacao(municipio.provedor)

    if municipio.provedor == "nacional_rest":
        raise ErroDeDriver(
            "nacional_rest",
            "usa o adaptador nacional (app/nfse/adapter.py), não o motor ABRASF",
        )

    if not municipio.url:
        raise ErroDeDriver(
            municipio.provedor,
            f"município {municipio.codigo_ibge} sem URL de webservice cadastrada",
        )

    if not municipio.fonte_url:
        # Sem fonte, a URL é chute — e chute em serviço fiscal não se registra (R8).
        raise ErroDeDriver(
            municipio.provedor,
            f"URL do município {municipio.codigo_ibge} sem fonte registrada; "
            "cadastre a fonte antes de emitir",
        )

    if not municipio.url.startswith("https://"):
        raise ErroDeDriver(
            municipio.provedor,
            "URL de webservice municipal precisa ser https; "
            f"recebido {municipio.url.split('://')[0]}://",
        )

    configuracao = ConfiguracaoAbrasf(
        url=municipio.url,
        namespace=municipio.namespace,
        versao_soap=municipio.versao_soap,
        encoding=municipio.encoding,
        assina_rps=municipio.assina_rps,
        assina_lote=municipio.assina_lote,
    )

    assinador = None
    if certificado is not None:
        assinador = assinador_de(certificado, alvo=alvo_assinatura)

    driver = AbrasfBaseDriver(configuracao=configuracao, transporte=transporte, assinador=assinador)
    driver.nome = municipio.provedor  # type: ignore[attr-defined]
    return driver
