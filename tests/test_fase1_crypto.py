"""Testes do envelope AES-256-GCM do cofre de certificados."""

from __future__ import annotations

import pytest
from app.core.crypto import (
    VERSAO_ENVELOPE,
    Cofre,
    ErroDeCriptografia,
    aad_do_tenant,
)

CHAVE = b"\x2a" * 32
CHAVE_ERRADA = b"\x3b" * 32


@pytest.fixture
def cofre() -> Cofre:
    return Cofre(CHAVE)


class TestEnvelope:
    def test_ida_e_volta(self, cofre: Cofre) -> None:
        original = b"conteudo do certificado A1 em DER"
        envelope = cofre.selar(original)
        assert envelope != original
        assert cofre.abrir(envelope) == original

    def test_envelope_comeca_com_versao(self, cofre: Cofre) -> None:
        assert cofre.selar(b"x").startswith(VERSAO_ENVELOPE)

    def test_nonce_diferente_a_cada_selagem(self, cofre: Cofre) -> None:
        a = cofre.selar(b"mesmo conteudo")
        b = cofre.selar(b"mesmo conteudo")
        assert a != b, "nonce aleatório deve impedir envelopes idênticos"

    def test_chave_errada_nao_abre(self, cofre: Cofre) -> None:
        envelope = cofre.selar(b"segredo")
        with pytest.raises(ErroDeCriptografia, match="não foi possível abrir"):
            Cofre(CHAVE_ERRADA).abrir(envelope)

    def test_adulteracao_e_detectada(self, cofre: Cofre) -> None:
        envelope = bytearray(cofre.selar(b"segredo"))
        envelope[-1] ^= 0xFF
        with pytest.raises(ErroDeCriptografia):
            cofre.abrir(bytes(envelope))

    def test_aad_divergente_nao_abre(self, cofre: Cofre) -> None:
        envelope = cofre.selar(b"segredo", aad=aad_do_tenant("tenant-a"))
        with pytest.raises(ErroDeCriptografia):
            cofre.abrir(envelope, aad=aad_do_tenant("tenant-b"))

    def test_aad_igual_abre(self, cofre: Cofre) -> None:
        aad = aad_do_tenant("tenant-a")
        envelope = cofre.selar(b"segredo", aad=aad)
        assert cofre.abrir(envelope, aad=aad) == b"segredo"

    def test_envelope_vazio_falha(self, cofre: Cofre) -> None:
        with pytest.raises(ErroDeCriptografia, match="vazio ou truncado"):
            cofre.abrir(b"")

    def test_envelope_truncado_falha(self, cofre: Cofre) -> None:
        with pytest.raises(ErroDeCriptografia, match="vazio ou truncado"):
            cofre.abrir(VERSAO_ENVELOPE + b"\x00" * 5)

    def test_versao_desconhecida_falha(self, cofre: Cofre) -> None:
        envelope = cofre.selar(b"x")
        adulterado = b"v9" + envelope[2:]
        with pytest.raises(ErroDeCriptografia, match="versão"):
            cofre.abrir(adulterado)

    def test_chave_de_tamanho_errado_nao_instancia(self) -> None:
        with pytest.raises(ErroDeCriptografia, match="32 bytes"):
            Cofre(b"curta")

    def test_conteudo_precisa_ser_bytes(self, cofre: Cofre) -> None:
        with pytest.raises(ErroDeCriptografia, match="bytes"):
            cofre.selar("texto")  # type: ignore[arg-type]


class TestAad:
    def test_aad_por_tenant_e_distinto(self) -> None:
        assert aad_do_tenant("a") != aad_do_tenant("b")
        assert aad_do_tenant("a") == b"tenant:a"
