"""Schemas de entrada de CT-e e MDF-e: validação de borda antes do gerador.

Passo 1 de 5 da exposição na API (auditoria §25). O gerador já recusa dados inválidos, mas
lança `ValueError`; a borda HTTP precisa de 422 com mensagem de campo. Estes testes cobrem a
conversão e as recusas — não a rota, que ainda não existe.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from app.cte import PapelTomador
from app.cte.schemas import CTeIn, ParteIn
from app.mdfe.schemas import MDFeIn
from pydantic import ValidationError

CHAVE = "52" + "0" * 42
CHAVE_DOC = "52" + "1" * 42


def parte(**extra) -> dict:
    base = {
        "nome": "EMPRESA TESTE",
        "cnpj": "11222333000181",
        "ie": "123456789",
        "municipio_ibge": "5208707",
        "municipio": "GOIANIA",
        "uf": "GO",
    }
    base.update(extra)
    return base


def cte(**extra) -> dict:
    base = {
        "numero": 1,
        "serie": 1,
        "chave": CHAVE,
        "emitente": parte(),
        "destinatario": parte(),
        "papel_tomador": "3",
        "valor_total": "100.00",
        "peso": "10.00",
        "produto": "CARGA",
        "data_emissao": "2026-11-26T12:00:00",
        "rntrc": "12345678",
        "chaves_documentos": [CHAVE_DOC],
    }
    base.update(extra)
    return base


class TestCTeIn:
    def test_converte_para_dominio(self) -> None:
        dados = CTeIn(**cte()).para_dominio()
        assert dados.chave == CHAVE
        assert dados.papel_tomador is PapelTomador.DESTINATARIO
        assert dados.emitente.cnpj == "11222333000181"

    def test_nao_aceita_tenant_no_corpo(self) -> None:
        # Regra dura do projeto: tenant vem da API key. O schema não tem o campo — provar isso
        # evita que alguém o adicione "para facilitar" no futuro.
        assert "tenant_id" not in CTeIn.model_fields

    def test_cnpj_com_letra_recusa(self) -> None:
        with pytest.raises(ValidationError, match="apenas dígitos"):
            CTeIn(**cte(emitente=parte(cnpj="1122233300018X")))

    def test_chave_curta_recusa(self) -> None:
        with pytest.raises(ValidationError):
            CTeIn(**cte(chave="123"))

    def test_chave_de_documento_invalida_recusa(self) -> None:
        with pytest.raises(ValidationError, match="44 dígitos"):
            CTeIn(**cte(chaves_documentos=["curta"]))

    def test_valor_zero_recusa(self) -> None:
        with pytest.raises(ValidationError):
            CTeIn(**cte(valor_total="0"))

    def test_sem_chave_de_documento_recusa(self) -> None:
        with pytest.raises(ValidationError):
            CTeIn(**cte(chaves_documentos=[]))

    def test_papel_tomador_invalido_recusa(self) -> None:
        with pytest.raises(ValidationError):
            CTeIn(**cte(papel_tomador="9"))

    def test_parte_sem_documento_vira_none(self) -> None:
        # `ParteIn` não exige documento; quem exige é o leiaute, conforme o papel do tomador.
        # O gerador recusa depois. Aqui só garantimos que a borda não inventa valor.
        modelo = ParteIn(**parte(cnpj=None))
        assert modelo.cnpj is None


class TestMDFeIn:
    def base(self, **extra) -> dict:
        dados = {
            "numero": 1,
            "serie": 1,
            "chave": CHAVE,
            "emitente": {
                "cnpj": "11222333000181",
                "nome": "EMPRESA TESTE",
                "ie": "123456789",
                "municipio_ibge": "5208707",
                "municipio": "GOIANIA",
                "uf": "GO",
            },
            "uf_inicio": "GO",
            "uf_fim": "GO",
            "municipios_carregamento": [{"codigo_ibge": "5208707", "nome": "GOIANIA"}],
            "valor_carga": "1000.00",
            "peso": "10.00",
            "data_emissao": "2026-11-26T12:00:00",
            "descargas": [{"codigo_ibge": "5208707", "nome": "GOIANIA", "chaves_nfe": [CHAVE_DOC]}],
        }
        dados.update(extra)
        return dados

    def test_converte_para_dominio(self) -> None:
        dados = MDFeIn(**self.base()).para_dominio()
        assert dados.emitente.cnpj == "11222333000181"
        assert dados.descargas[0].chaves_nfe == (CHAVE_DOC,)

    def test_nao_aceita_tenant_no_corpo(self) -> None:
        assert "tenant_id" not in MDFeIn.model_fields

    def test_sem_descarga_recusa(self) -> None:
        with pytest.raises(ValidationError):
            MDFeIn(**self.base(descargas=[]))

    def test_descarga_sem_chave_recusa(self) -> None:
        with pytest.raises(ValidationError):
            MDFeIn(
                **self.base(
                    descargas=[{"codigo_ibge": "5208707", "nome": "GOIANIA", "chaves_nfe": []}]
                )
            )

    def test_chave_de_nfe_invalida_recusa(self) -> None:
        with pytest.raises(ValidationError, match="44 dígitos"):
            MDFeIn(
                **self.base(
                    descargas=[{"codigo_ibge": "5208707", "nome": "GOIANIA", "chaves_nfe": ["x"]}]
                )
            )


class TestRoundTripComGerador:
    """Prova que o schema alimenta o gerador de verdade — não é DTO decorativo."""

    def test_cte_do_schema_gera_xml_valido(self) -> None:
        from app.certificates.cofre import CertificadoA1
        from app.cte.gerador import gerar_assinado

        from tests.test_fase2_certificado import SENHA, gerar_pfx

        cert = CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())
        dados = CTeIn(**cte(data_emissao=datetime(2026, 11, 26, 12, 0))).para_dominio()
        xml = gerar_assinado(dados, cert)
        assert b"Signature" in xml

    def test_mdfe_do_schema_gera_xml_valido(self) -> None:
        from app.certificates.cofre import CertificadoA1
        from app.mdfe.gerador import gerar_assinado

        from tests.test_fase2_certificado import SENHA, gerar_pfx

        cert = CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())
        bruto = TestMDFeIn().base(
            valor_carga=Decimal("1000.00"), data_emissao=datetime(2026, 11, 26, 12, 0)
        )
        dados = MDFeIn(**bruto).para_dominio()
        xml = gerar_assinado(dados, cert)
        assert b"Signature" in xml
