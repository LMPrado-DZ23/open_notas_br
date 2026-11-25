"""Validação estrutural da DPS contra o XSD oficial (offline e reproduzível).

Este é o teste de contrato mais forte do projeto sem depender de rede: o XSD
oficial publicado define forma, ordem e cardinalidade dos elementos. Se a DPS aqui
gerada valida, erro de estrutura está descartado antes de qualquer chamada à SEFIN.

O que ele **não** prova: aceitação pela SEFIN. Validação de schema é forma; regra
de negócio (cadastro do município, serviço, alíquota) é outra camada.

Schemas em `tests/fixtures/schemas/nfse-1.01/` — ver `ORIGEM.md`.
"""

from __future__ import annotations

import pathlib
from datetime import datetime
from decimal import Decimal

import pytest
from app.db.models.enums import AmbienteFiscal
from app.nfse.constants import FUSO_BR
from app.nfse.dps import DpsInput, Prestador, Tomador, dps_para_bytes
from app.nfse.signer import assinar_dps
from lxml import etree

from tests.test_fase2_certificado import SENHA, gerar_pfx

SCHEMAS = pathlib.Path(__file__).resolve().parent / "fixtures" / "schemas" / "nfse-1.01"


@pytest.fixture(scope="module")
def schema_dps() -> etree.XMLSchema:
    caminho = SCHEMAS / "DPS_v1.01.xsd"
    if not caminho.is_file():  # pragma: no cover - fixture versionada
        pytest.skip(f"schema ausente: {caminho}")
    return etree.XMLSchema(etree.parse(str(caminho)))


@pytest.fixture(scope="module")
def certificado():
    from app.certificates.cofre import CertificadoA1

    return CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())


def entrada(cnpj: str = "11222333000181", **extra) -> DpsInput:
    base = {
        "ambiente": AmbienteFiscal.HOMOLOGACAO,
        "c_mun_emissor": "3550308",
        "serie": 1,
        "n_dps": 1,
        "dh_emi": datetime(2026, 11, 25, 12, 0, tzinfo=FUSO_BR),
        "prestador": Prestador(documento=cnpj),
        "tomador": Tomador(nome="Tomador de Teste", documento="11144477735"),
        "c_trib_nac": "010701",
        "x_desc_serv": "Servico de teste",
        "valor": Decimal("10.00"),
    }
    base.update(extra)
    return DpsInput(**base)


class TestSchemaDps:
    def test_dps_gerada_valida(self, schema_dps: etree.XMLSchema) -> None:
        doc = etree.fromstring(dps_para_bytes(entrada()))
        assert schema_dps.validate(doc), [
            f"linha {e.line}: {e.message}" for e in list(schema_dps.error_log)[:5]
        ]

    def test_dps_assinada_valida(self, schema_dps: etree.XMLSchema, certificado) -> None:
        # A versão assinada é a que efetivamente vai à SEFIN: é ela que precisa
        # validar, com o grupo Signature dentro de infDPS.
        assinada = assinar_dps(dps_para_bytes(entrada()), certificado)
        doc = etree.fromstring(assinada)
        assert schema_dps.validate(doc), [
            f"linha {e.line}: {e.message}" for e in list(schema_dps.error_log)[:5]
        ]

    def test_com_ibscbs_valida(self, schema_dps: etree.XMLSchema, certificado) -> None:
        from app.nfse.dps import Ibscbs

        com_ibs = entrada(
            ibscbs=Ibscbs(c_ind_op="100301", c_class_trib="000001", c_nbs="123456789")
        )
        doc = etree.fromstring(dps_para_bytes(com_ibs))
        assert schema_dps.validate(doc), [
            f"linha {e.line}: {e.message}" for e in list(schema_dps.error_log)[:5]
        ]

    def test_dps_invalida_e_recusada_pelo_schema(self, schema_dps: etree.XMLSchema) -> None:
        """O schema precisa RECUSAR estrutura errada — senão o teste acima é vazio."""
        doc = etree.fromstring(dps_para_bytes(entrada()))
        # Remove o grupo obrigatório de valores.
        ns = doc.nsmap.get(None)
        for elemento in doc.iter(f"{{{ns}}}valores"):
            elemento.getparent().remove(elemento)
            break
        assert not schema_dps.validate(doc), "schema aceitou DPS sem o grupo valores"

    def test_chave_estrangeira_nao_afeta(self, schema_dps: etree.XMLSchema) -> None:
        # CNPJ alfanumérico: o XSD 1.01 usa padrão numérico. Este teste DOCUMENTA a
        # limitação em vez de esconder: se falhar, é o schema que ainda não cobre
        # alfanumérico, não a DPS.
        alfa = entrada(cnpj="12ABC34501DE35")
        doc = etree.fromstring(dps_para_bytes(alfa))
        valido = schema_dps.validate(doc)
        if not valido:
            erros = " ".join(e.message for e in list(schema_dps.error_log)[:3])
            assert "12ABC34501DE35" in erros or "pattern" in erros.lower(), (
                "falha de validação não relacionada ao CNPJ alfanumérico: " + erros
            )
