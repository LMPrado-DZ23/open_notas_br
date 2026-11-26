"""Cadastro de municípios para NFS-e multi-prefeitura.

Seção 2.1 do v10.0. Os campos não são decorativos: cada um resolve um problema que
aparece na prática.

- `provedor` decide qual driver responde. Sem ele, o roteamento viraria `if municipio ==`.
- `encoding` existe porque provedores legados (GINFES, DSF) usam ISO-8859-1; mandar
  UTF-8 para eles corrompe acentuação no XML.
- `exige_credencial_municipal`, `assina_rps`, `assina_lote` variam por provedor e mudam o
  payload. Presumir um padrão único gera lote recusado.
- `fonte_url` é obrigatória (R3): URL sem origem rastreável não entra.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, MixinTimestamps


class ProvedorNFSe(enum.StrEnum):
    """Provedor/layout que responde pelo município."""

    NACIONAL_REST = "nacional_rest"
    ABRASF_1_0 = "abrasf_1_0"
    ABRASF_2_01 = "abrasf_2_01"
    ABRASF_2_02 = "abrasf_2_02"
    ABRASF_2_03 = "abrasf_2_03"
    ABRASF_2_04 = "abrasf_2_04"
    ABRASF_2_06 = "abrasf_2_06"
    GOIANIA = "goiania"
    GINFES = "ginfes"
    ISSNET = "issnet"
    BETHA = "betha"
    WEBISS = "webiss"
    SIMPLISS = "simpliss"
    DSF = "dsf"
    PRODATA = "proddata"
    CENTRI = "centri"
    FISCO_SIMPLEX = "fisco_simplex"
    CONAM = "conam"
    COPLAN = "coplan"
    DIGIFRED = "digifred"
    EL = "el"
    ELOTECH = "elotech"
    FIORILLI = "fiorilli"
    FUTURIZE = "futurize"
    GISS = "giss"
    GOVDIGITAL = "govdigital"
    IPM = "ipm"
    ISSINTEL = "issintel"
    MEGASOFT = "megasoft"
    PRONIM = "pronim"
    SAATRI = "saatri"
    SH3 = "sh3"
    SIGCORP = "sigcorp"
    SIGISSWEB = "sigissweb"
    SINTESE = "sintese"
    TINUS = "tinus"


class EncodingXML(enum.StrEnum):
    UTF8 = "UTF-8"
    ISO8859_1 = "ISO-8859-1"


class MunicipioNFSe(Base, MixinTimestamps):
    """Um município e o que ele exige para emitir."""

    __tablename__ = "municipios_nfse"

    #: Código IBGE de 7 dígitos. É a PK natural: nome de município se repete entre UFs.
    codigo_ibge: Mapped[str] = mapped_column(String(7), primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    uf: Mapped[str] = mapped_column(String(2), nullable=False, index=True)

    provedor: Mapped[ProvedorNFSe] = mapped_column(
        Enum(ProvedorNFSe, name="provedor_nfse", native_enum=False, length=24),
        nullable=False,
        index=True,
    )
    versao_layout: Mapped[str | None] = mapped_column(String(16))

    url_homologacao: Mapped[str | None] = mapped_column(String(512))
    url_producao: Mapped[str | None] = mapped_column(String(512))
    namespace_xml: Mapped[str | None] = mapped_column(String(512))

    exige_credencial_municipal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    assina_rps: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    assina_lote: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    encoding: Mapped[EncodingXML] = mapped_column(
        Enum(EncodingXML, name="encoding_xml", native_enum=False, length=12),
        nullable=False,
        default=EncodingXML.UTF8,
        server_default=EncodingXML.UTF8.value,
    )

    #: Já passou por emissão real de ponta a ponta. Padrão falso: nada é "homologado"
    #: por estar cadastrado.
    homologado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    #: Portal oficial de onde vieram URL e leiaute (R3). Obrigatório de propósito.
    fonte_url: Mapped[str] = mapped_column(String(512), nullable=False)
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("codigo_ibge ~ '^[0-9]{7}$'", name="ck_municipios_nfse_ibge_7_digitos"),
        CheckConstraint("uf ~ '^[A-Z]{2}$'", name="ck_municipios_nfse_uf_2_letras"),
        # R3: URL só entra em https. `http://` em serviço fiscal é falha de segurança
        # (dado e credencial em texto claro), não detalhe de configuração.
        CheckConstraint(
            "url_homologacao IS NULL OR url_homologacao LIKE 'https://%'",
            name="ck_municipios_nfse_homolog_https",
        ),
        CheckConstraint(
            "url_producao IS NULL OR url_producao LIKE 'https://%'",
            name="ck_municipios_nfse_producao_https",
        ),
        CheckConstraint("fonte_url LIKE 'https://%'", name="ck_municipios_nfse_fonte_https"),
    )

    def __repr__(self) -> str:  # pragma: no cover - diagnóstico
        return f"<MunicipioNFSe {self.codigo_ibge} {self.nome}/{self.uf} {self.provedor}>"
