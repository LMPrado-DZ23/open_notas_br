"""Endpoints de webservice da SEFAZ por UF, ambiente e serviço.

Seção 2.1 item 3 do v10.0. Tabela, não constante no código: cada UF tem endpoint
próprio, e hardcodar URL é exatamente o que a R3/P2 proíbe.

`fonte_url` é NOT NULL porque um endpoint por UF só é confiável se der para mostrar de
onde veio. Sem isso, uma URL errada vira rejeição fiscal sem causa identificável.
"""

from __future__ import annotations

import enum

from sqlalchemy import CheckConstraint, Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, MixinTimestamps


class ServicoSefaz(enum.StrEnum):
    """Serviços que o gateway consome. Extensível por natureza."""

    NFE_AUTORIZACAO = "NFeAutorizacao"
    NFE_RET_AUTORIZACAO = "NFeRetAutorizacao"
    NFE_STATUS = "NFeStatusServico"
    NFE_DISTRIBUICAO = "NFeDistribuicaoDFe"
    NFE_RECEPCAO_EVENTO = "NFeRecepcaoEvento"
    NFE_INUTILIZACAO = "NFeInutilizacao"
    CTE_RECEPCAO_SINC = "CTeRecepcaoSinc"
    CTE_RECEPCAO_EVENTO = "CTeRecepcaoEvento"
    MDFE_RECEPCAO_SINC = "MDFeRecepcaoSinc"
    MDFE_RECEPCAO_EVENTO = "MDFeRecepcaoEvento"


class VersaoSOAP(enum.StrEnum):
    SOAP_11 = "1.1"
    SOAP_12 = "1.2"


class WebserviceSefaz(Base, MixinTimestamps):
    """Um endpoint por UF, ambiente e serviço."""

    __tablename__ = "webservices_sefaz"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    #: cUF do IBGE. 52 = SVRS (virtual, atende GO e mais 13 UFs).
    uf: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    #: 1 = produção, 2 = homologação.
    ambiente: Mapped[str] = mapped_column(String(1), nullable=False)
    servico: Mapped[ServicoSefaz] = mapped_column(
        Enum(ServicoSefaz, name="servico_sefaz", native_enum=False, length=32),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    versao_soap: Mapped[VersaoSOAP] = mapped_column(
        Enum(VersaoSOAP, name="versao_soap", native_enum=False, length=8),
        nullable=False,
        default=VersaoSOAP.SOAP_12,
        server_default=VersaoSOAP.SOAP_12.value,
    )
    versao_layout: Mapped[str | None] = mapped_column(String(16))
    #: Portal oficial de origem (R3/P2). Obrigatório.
    fonte_url: Mapped[str] = mapped_column(String(512), nullable=False)
    #: Autorizador que responde de fato (ex.: "SVRS", "SP", "MG"). Útil na operação.
    autorizador: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (
        UniqueConstraint("uf", "ambiente", "servico", name="uq_webservices_sefaz_endpoint"),
        CheckConstraint("ambiente IN ('1','2')", name="ck_webservices_sefaz_ambiente"),
        CheckConstraint("url LIKE 'https://%'", name="ck_webservices_sefaz_url_https"),
        CheckConstraint("fonte_url LIKE 'https://%'", name="ck_webservices_sefaz_fonte_https"),
    )

    def __repr__(self) -> str:  # pragma: no cover - diagnóstico
        return f"<WebserviceSefaz {self.uf}/{self.ambiente} {self.servico}>"
