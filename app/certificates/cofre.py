"""Cofre do certificado digital A1 (.pfx/.p12).

Responsabilidades:

1. Abrir o PFX com a senha e extrair metadados úteis (CNPJ, razão social,
   validade, série, fingerprint).
2. Montar o contexto TLS de mTLS que a SEFIN exige.
3. Selar o PFX para persistência com AES-256-GCM, para que o arquivo em claro
   nunca toque o disco do serviço.

**Compromisso técnico declarado:** o `ssl` da biblioteca padrão só carrega
certificado de cliente a partir de **arquivo** (`SSLContext.load_cert_chain`). Para
não guardar o PFX em claro, escrevemos PEM em diretório temporário privado (0700,
arquivos 0600), carregamos o contexto e apagamos o diretório **antes** da primeira
requisição — o contexto já tem o certificado em memória. A janela em disco é de
milissegundos e restrita ao diretório temporário do processo; não há API pública
em Python que elimine essa janela.
"""

from __future__ import annotations

import contextlib
import hashlib
import re
import ssl
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from cryptography.x509.oid import NameOID

#: OID do CNPJ no SAN (padrão ICP-Brasil para e-CNPJ).
OID_CNPJ = x509.ObjectIdentifier("2.16.76.1.3.3")

_RE_CNPJ = re.compile(r"\b(\d{14})\b")
_RE_CNPJ_ALFA = re.compile(r"\b([0-9A-Z]{12}\d{2})\b")


class ErroCertificado(Exception):
    """Falha ao abrir ou usar o certificado A1."""


@dataclass(frozen=True)
class CertificadoA1:
    """Certificado A1 desbloqueado em memória.

    Os campos PEM e DER ficam fora do `repr` para que um `print` acidental de
    objeto nunca despeje material de chave em log.
    """

    cnpj: str | None
    razao_social: str | None
    emissor: str | None
    numero_serie: str | None
    valido_de: datetime
    valido_ate: datetime
    fingerprint_sha256: str
    _cert_pem: bytes = field(repr=False)
    _key_pem: bytes = field(repr=False)
    _cadeia_pem: tuple[bytes, ...] = field(default=(), repr=False)

    # -- construção ----------------------------------------------------
    @classmethod
    def de_pfx(cls, pfx: bytes, senha: str | bytes | None = None) -> CertificadoA1:
        """Abre um PFX/P12 e devolve o certificado pronto para uso.

        Levanta :class:`ErroCertificado` para arquivo vazio, senha errada ou
        conteúdo que não é PKCS#12.
        """
        if not pfx:
            raise ErroCertificado("arquivo de certificado vazio")

        senha_bytes = senha.encode("utf-8") if isinstance(senha, str) else senha
        if senha_bytes == b"":
            senha_bytes = None

        try:
            chave, certificado, extras = load_key_and_certificates(pfx, senha_bytes)
        except ValueError as exc:
            raise ErroCertificado(
                "não foi possível abrir o certificado: senha incorreta ou arquivo "
                "que não é PKCS#12 (.pfx/.p12)"
            ) from exc

        if certificado is None or chave is None:
            raise ErroCertificado("o arquivo PKCS#12 não contém par de certificado e chave privada")

        cert_pem = certificado.public_bytes(Encoding.PEM)
        key_pem = chave.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption(),
        )
        cadeia = tuple(c.public_bytes(Encoding.PEM) for c in (extras or []))

        fingerprint = certificado.fingerprint(hashes.SHA256()).hex()
        cnpj = _extrair_cnpj(certificado)

        return cls(
            cnpj=cnpj,
            razao_social=_atributo(certificado, NameOID.COMMON_NAME),
            emissor=_atributo(certificado, NameOID.ORGANIZATION_NAME)
            or (certificado.issuer.rfc4514_string() or None),
            numero_serie=format(certificado.serial_number, "X"),
            valido_de=certificado.not_valid_before_utc,
            valido_ate=certificado.not_valid_after_utc,
            fingerprint_sha256=fingerprint,
            _cert_pem=cert_pem,
            _key_pem=key_pem,
            _cadeia_pem=cadeia,
        )

    # -- estado --------------------------------------------------------
    @property
    def expirado(self) -> bool:
        return datetime.now(UTC) >= self.valido_ate

    @property
    def dias_restantes(self) -> int:
        return (self.valido_ate - datetime.now(UTC)).days

    def saude(self) -> dict[str, object]:
        """Resumo seguro para expor na API — sem material de chave."""
        return {
            "cnpj": self.cnpj,
            "razao_social": self.razao_social,
            "emissor": self.emissor,
            "numero_serie": self.numero_serie,
            "valido_de": self.valido_de.isoformat(),
            "valido_ate": self.valido_ate.isoformat(),
            "dias_restantes": self.dias_restantes,
            "expirado": self.expirado,
            "fingerprint_sha256": self.fingerprint_sha256,
        }

    def impressao_arquivo(self) -> str:
        """SHA-256 do DER do certificado, para deduplicar uploads."""
        return hashlib.sha256(self._cert_pem).hexdigest()

    # -- uso -----------------------------------------------------------
    def ssl_context(self) -> ssl.SSLContext:
        """Contexto TLS de mTLS com o certificado de cliente carregado.

        Escreve PEM em diretório temporário privado, carrega no contexto e remove
        o diretório. O contexto retornado já carrega o certificado em memória.
        """
        contexto = ssl.create_default_context()
        contexto.minimum_version = ssl.TLSVersion.TLSv1_2

        with _diretorio_privado() as pasta:
            arquivo_cert = pasta / "cert.pem"
            arquivo_chave = pasta / "key.pem"
            _escrever_privado(arquivo_cert, b"".join((self._cert_pem, *self._cadeia_pem)))
            _escrever_privado(arquivo_chave, self._key_pem)
            contexto.load_cert_chain(certfile=str(arquivo_cert), keyfile=str(arquivo_chave))

        return contexto


def _atributo(certificado: x509.Certificate, oid: x509.ObjectIdentifier) -> str | None:
    valores = certificado.subject.get_attributes_for_oid(oid)
    if not valores:
        return None
    valor = valores[0].value
    return str(valor).strip() or None


def _extrair_cnpj(certificado: x509.Certificate) -> str | None:
    """Busca o CNPJ no SAN (OID ICP-Brasil) e, na falta, no subject."""
    try:
        san = certificado.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        for outro in san.value.get_values_for_type(x509.OtherName):
            if outro.type_id == OID_CNPJ:
                texto = outro.value.decode("utf-8", errors="ignore").strip()
                limpo = re.sub(r"\D", "", texto)
                if len(limpo) == 14:
                    return limpo
    except x509.ExtensionNotFound:
        pass

    for oid in (OID_CNPJ, NameOID.COMMON_NAME, NameOID.ORGANIZATION_NAME):
        valor = _atributo(certificado, oid)
        if not valor:
            continue
        achado = _RE_CNPJ.search(valor)
        if achado:
            return achado.group(1)
        achado_alfa = _RE_CNPJ_ALFA.search(valor.upper())
        if achado_alfa:
            return achado_alfa.group(1)

    return None


@contextmanager
def _diretorio_privado() -> Iterator[Path]:
    """Diretório temporário com permissão 0700, apagado ao sair."""
    with tempfile.TemporaryDirectory(prefix="notasbr-tls-") as bruto:
        pasta = Path(bruto)
        # chmod de diretório não é POSIX no Windows: sem efeito lá, essencial aqui.
        with contextlib.suppress(OSError, NotImplementedError):
            pasta.chmod(0o700)
        yield pasta


def _escrever_privado(caminho: Path, conteudo: bytes) -> None:
    """Escreve arquivo com permissão 0600 antes de gravar o conteúdo."""
    descritor = None
    try:
        descritor = caminho.open("wb")
        with contextlib.suppress(OSError, NotImplementedError):
            caminho.chmod(0o600)
        descritor.write(conteudo)
        descritor.flush()
    finally:
        if descritor is not None:
            descritor.close()


def selar_pfx(pfx: bytes, *, tenant_id: object, chave: bytes, senha: bytes | None = None) -> bytes:
    """Sela o PFX (e a senha, se houver) para persistência.

    Formato do conteúdo selado::

        tamanho_do_pfx(4 bytes, big-endian) + pfx + senha

    Prefixo de tamanho em vez de separador porque PFX é binário e contém `0x00` em
    qualquer posição — um separador de byte truncaria o certificado.

    O `aad` amarra o envelope ao tenant: um blob copiado para outra conta não abre.
    """
    from app.core.crypto import Cofre, aad_do_tenant

    corpo = len(pfx).to_bytes(4, "big") + pfx + (senha or b"")
    return Cofre(chave).selar(corpo, aad=aad_do_tenant(tenant_id))


def abrir_pfx(
    envelope: bytes, *, tenant_id: object, chave: bytes, tem_senha: bool = False
) -> tuple[bytes, bytes | None]:
    """Abre o envelope selado devolvendo ``(pfx, senha)``."""
    from app.core.crypto import Cofre, aad_do_tenant

    corpo = Cofre(chave).abrir(envelope, aad=aad_do_tenant(tenant_id))
    if len(corpo) < 4:
        raise ErroCertificado("envelope de certificado truncado")
    tamanho = int.from_bytes(corpo[:4], "big")
    if tamanho <= 0 or 4 + tamanho > len(corpo):
        raise ErroCertificado("envelope de certificado inconsistente")
    pfx = corpo[4 : 4 + tamanho]
    if not tem_senha:
        return pfx, None
    return pfx, (corpo[4 + tamanho :] or None)
