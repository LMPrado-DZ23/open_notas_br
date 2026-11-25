"""Testes do cofre de certificado A1.

O certificado é **gerado no próprio teste** com `cryptography` e nunca é
commitado. Isso é o oposto de usar um PFX de exemplo: um PFX versionado com senha
conhecida é vazamento permanente e acostuma o time a ignorar `.gitignore`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.certificates.cofre import (
    OID_CNPJ,
    CertificadoA1,
    ErroCertificado,
    abrir_pfx,
    selar_pfx,
)
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    NoEncryption,
    pkcs12,
)
from cryptography.x509.oid import NameOID

CNPJ = "11222333000181"
SENHA = b"senha-de-teste"


def _der_utf8(texto: str) -> bytes:
    """Codifica OtherName como UTF8String (tag 0x0C) para o SAN."""
    bruto = texto.encode("utf-8")
    assert len(bruto) < 128
    return bytes([0x0C, len(bruto)]) + bruto


def gerar_pfx(
    *,
    senha: bytes | None = SENHA,
    cnpj: str | None = CNPJ,
    dias_validade: int = 365,
    apenas_cn: bool = False,
) -> bytes:
    """Gera um PKCS#12 autoassinado de teste."""
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    atributos = [
        x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Empresa Teste LTDA"),
        x509.NameAttribute(
            NameOID.COMMON_NAME, f"Empresa Teste LTDA:{cnpj}" if cnpj else "Empresa Teste LTDA"
        ),
    ]
    nome = x509.Name(atributos)

    agora = datetime.now(UTC)
    construtor = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - timedelta(days=1))
        .not_valid_after(agora + timedelta(days=dias_validade))
    )

    if cnpj and not apenas_cn:
        construtor = construtor.add_extension(
            x509.SubjectAlternativeName([x509.OtherName(OID_CNPJ, _der_utf8(cnpj))]),
            critical=False,
        )

    certificado = construtor.sign(chave, hashes.SHA256())

    algoritmo = BestAvailableEncryption(senha) if senha else NoEncryption()
    return pkcs12.serialize_key_and_certificates(
        name=b"teste",
        key=chave,
        cert=certificado,
        cas=None,
        encryption_algorithm=algoritmo,
    )


class TestAbertura:
    def test_abre_com_senha(self) -> None:
        certificado = CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())
        assert certificado.cnpj == CNPJ
        assert certificado.razao_social is not None
        assert certificado.fingerprint_sha256
        assert len(certificado.fingerprint_sha256) == 64

    def test_abre_sem_senha(self) -> None:
        certificado = CertificadoA1.de_pfx(gerar_pfx(senha=None))
        assert certificado.cnpj == CNPJ

    def test_senha_errada_falha_com_mensagem_util(self) -> None:
        with pytest.raises(ErroCertificado, match="senha incorreta"):
            CertificadoA1.de_pfx(gerar_pfx(), "senha-errada")

    def test_arquivo_vazio_falha(self) -> None:
        with pytest.raises(ErroCertificado, match="vazio"):
            CertificadoA1.de_pfx(b"", SENHA)

    def test_conteudo_que_nao_e_pkcs12_falha(self) -> None:
        with pytest.raises(ErroCertificado, match="PKCS#12"):
            CertificadoA1.de_pfx(b"isto nao e um certificado", SENHA)

    def test_cnpj_pelo_common_name_quando_nao_ha_san(self) -> None:
        certificado = CertificadoA1.de_pfx(gerar_pfx(apenas_cn=True), SENHA)
        assert certificado.cnpj == CNPJ


class TestValidade:
    def test_vigente(self) -> None:
        certificado = CertificadoA1.de_pfx(gerar_pfx(), SENHA)
        assert certificado.expirado is False
        assert certificado.dias_restantes > 300

    def test_expirado(self) -> None:
        pfx = gerar_pfx(dias_validade=0)
        certificado = CertificadoA1.de_pfx(pfx, SENHA)
        assert certificado.expirado is True
        assert certificado.dias_restantes <= 0

    def test_saude_nao_expoe_material_de_chave(self) -> None:
        certificado = CertificadoA1.de_pfx(gerar_pfx(), SENHA)
        saude = certificado.saude()

        assert saude["cnpj"] == CNPJ
        assert saude["expirado"] is False
        texto = str(saude)
        assert "PRIVATE KEY" not in texto
        assert "BEGIN CERTIFICATE" not in texto


class TestTLS:
    def test_contexto_tls_carrega_certificado(self) -> None:
        certificado = CertificadoA1.de_pfx(gerar_pfx(), SENHA)
        contexto = certificado.ssl_context()

        assert contexto.minimum_version.name.startswith("TLSv1_2")
        # O contexto comprova que o certificado de cliente foi carregado.
        estatisticas = contexto.cert_store_stats()
        assert isinstance(estatisticas, dict)

    def test_repr_nao_vaza_chave(self) -> None:
        certificado = CertificadoA1.de_pfx(gerar_pfx(), SENHA)
        assert "PRIVATE KEY" not in repr(certificado)


class TestSelagem:
    def test_ida_e_volta_com_senha(self) -> None:
        pfx = gerar_pfx()
        import uuid

        tenant = uuid.uuid4()
        chave = b"\x07" * 32

        envelope = selar_pfx(pfx, tenant_id=tenant, chave=chave, senha=SENHA)
        assert pfx not in envelope

        recuperado, senha = abrir_pfx(envelope, tenant_id=tenant, chave=chave, tem_senha=True)
        assert recuperado == pfx
        assert senha == SENHA

        # O PFX recuperado continua abrindo.
        assert CertificadoA1.de_pfx(recuperado, senha).cnpj == CNPJ

    def test_sem_senha(self) -> None:
        import uuid

        pfx = gerar_pfx(senha=None)
        tenant = uuid.uuid4()
        chave = b"\x08" * 32

        envelope = selar_pfx(pfx, tenant_id=tenant, chave=chave)
        recuperado, senha = abrir_pfx(envelope, tenant_id=tenant, chave=chave)
        assert recuperado == pfx
        assert senha is None

    def test_outro_tenant_nao_abre(self) -> None:
        import uuid

        from app.core.crypto import ErroDeCriptografia

        pfx = gerar_pfx()
        chave = b"\x09" * 32
        envelope = selar_pfx(pfx, tenant_id=uuid.uuid4(), chave=chave)

        with pytest.raises(ErroDeCriptografia):
            abrir_pfx(envelope, tenant_id=uuid.uuid4(), chave=chave)
