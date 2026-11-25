"""Testes do verificador de assinatura com falha explícita.

Existem porque `verificar` devolve booleano e um retorno ignorado vira falso
positivo silencioso — aconteceu na prática durante um diagnóstico, onde um script
chamou `verificar(xml, cert)` sem usar o resultado e concluiu "adulteração
aceita". `exigir_assinatura_valida` fecha essa porta.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from app.db.models.enums import AmbienteFiscal
from app.nfse.constants import FUSO_BR
from app.nfse.dps import DpsInput, Prestador, dps_para_bytes
from app.nfse.signer import ErroAssinatura, assinar_dps, exigir_assinatura_valida, verificar

from tests.test_fase2_certificado import SENHA, gerar_pfx


@pytest.fixture(scope="module")
def certificado():
    from app.certificates.cofre import CertificadoA1

    return CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())


@pytest.fixture(scope="module")
def dps_assinada(certificado):
    entrada = DpsInput(
        ambiente=AmbienteFiscal.HOMOLOGACAO,
        c_mun_emissor="3550308",
        serie=1,
        n_dps=1,
        dh_emi=datetime(2026, 11, 25, 12, 0, tzinfo=FUSO_BR),
        prestador=Prestador(documento="11222333000181"),
        c_trib_nac="010701",
        x_desc_serv="Servico de teste",
        valor=Decimal("10.00"),
    )
    return assinar_dps(dps_para_bytes(entrada), certificado)


class TestVerificar:
    def test_original_valida(self, dps_assinada: bytes, certificado) -> None:
        assert verificar(dps_assinada, certificado) is True

    def test_adulterada_invalida(self, dps_assinada: bytes, certificado) -> None:
        adulterada = dps_assinada.replace(b"Servico de teste", b"Servico de tes7e")
        assert verificar(adulterada, certificado) is False

    def test_sem_certificado_levanta(self, dps_assinada: bytes) -> None:
        with pytest.raises(ErroAssinatura, match="exige o certificado"):
            verificar(dps_assinada, None)


class TestExigir:
    def test_passa_quando_valida(self, dps_assinada: bytes, certificado) -> None:
        exigir_assinatura_valida(dps_assinada, certificado)  # não levanta

    def test_levanta_quando_adulterada(self, dps_assinada: bytes, certificado) -> None:
        # O ponto do teste: sem usar o retorno, o erro precisa aparecer.
        adulterada = dps_assinada.replace(b"Servico de teste", b"Servico de tes7e")
        with pytest.raises(ErroAssinatura, match="não confere"):
            exigir_assinatura_valida(adulterada, certificado)

    def test_levanta_com_certificado_errado(self, dps_assinada: bytes) -> None:
        from app.certificates.cofre import CertificadoA1

        outro = CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())
        with pytest.raises(ErroAssinatura):
            exigir_assinatura_valida(dps_assinada, outro)
