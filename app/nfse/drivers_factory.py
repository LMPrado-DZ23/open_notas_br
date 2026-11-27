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
from typing import Any, Literal

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


Ambiente = Literal["homologacao", "producao"]


def de_municipio(
    row: Any, *, ambiente: Ambiente = "homologacao", versao_soap: str = "1.2"
) -> MunicipioParaDriver:
    """Mapeia a linha de `municipios_nfse` para a configuração da fábrica.

    O `ambiente` escolhe qual URL usar. **Sem default esperto**: produção não é escolhida
    por omissão — emitir em produção por acidente é irreversível.

    `namespace_xml` nulo no cadastro levanta: inventar namespace produz XML que o provedor
    recusa sem dizer por quê.

    **`versao_soap` é parâmetro, não dedução.** É tentador inferir "ABRASF 1.0 usa SOAP 1.1"
    pelo nome do provedor, e eu cheguei a escrever isso — mas não há fonte no repositório
    confirmando a regra por provedor, e um 1.1 trocado por 1.2 faz o provedor recusar o
    envelope inteiro. Quem sabe a versão é o manual do município; até ele ser cadastrado,
    o padrão é 1.2 e a escolha fica explícita em quem chama.
    """
    url = row.url_homologacao if ambiente == "homologacao" else row.url_producao
    namespace = row.namespace_xml
    if not namespace:
        raise ErroDeDriver(
            str(row.provedor),
            f"município {row.codigo_ibge} sem namespace_xml no cadastro",
        )

    # `EncodingXML` e `ProvedorNFSe` são enums do ORM; a fábrica trabalha com texto.
    encoding = getattr(row.encoding, "value", row.encoding)
    provedor = getattr(row.provedor, "value", row.provedor)

    return MunicipioParaDriver(
        codigo_ibge=row.codigo_ibge,
        provedor=provedor,
        url=url,
        namespace=namespace,
        versao_soap=versao_soap,
        encoding=encoding,
        assina_rps=bool(row.assina_rps),
        assina_lote=bool(row.assina_lote),
        fonte_url=row.fonte_url,
    )


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
    driver.nome = municipio.provedor
    return driver
