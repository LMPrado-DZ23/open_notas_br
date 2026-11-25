"""Criptografia simétrica do cofre de certificados (AES-256-GCM).

Formato do envelope selado, versionado para permitir rotação futura::

    b"v1" + nonce(12) + ciphertext+tag

O `aad` (dados autenticados adicionais) amarra o envelope ao seu dono: selar com
`aad=b"tenant:<uuid>"` faz com que o blob só abra no contexto daquele tenant, e
impede que um envelope válido seja movido de uma linha para outra do banco.

Nada aqui loga, imprime ou inclui o conteúdo em mensagem de erro.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSAO_ENVELOPE = b"v1"
TAMANHO_NONCE = 12
TAMANHO_CHAVE = 32


class ErroDeCriptografia(Exception):
    """Falha ao selar ou abrir um envelope."""


@dataclass(frozen=True, slots=True)
class Cofre:
    """Cifra e decifra blobs com AES-256-GCM."""

    chave: bytes

    def __post_init__(self) -> None:
        if len(self.chave) != TAMANHO_CHAVE:
            raise ErroDeCriptografia(
                f"chave deve ter {TAMANHO_CHAVE} bytes para AES-256; tem {len(self.chave)}"
            )

    def selar(self, conteudo: bytes, *, aad: bytes = b"") -> bytes:
        """Cifra `conteudo` e devolve o envelope versionado."""
        if not isinstance(conteudo, (bytes, bytearray)):
            raise ErroDeCriptografia("conteúdo a selar deve ser bytes")
        nonce = os.urandom(TAMANHO_NONCE)
        cifrado = AESGCM(self.chave).encrypt(nonce, bytes(conteudo), aad or None)
        return VERSAO_ENVELOPE + nonce + cifrado

    def abrir(self, envelope: bytes, *, aad: bytes = b"") -> bytes:
        """Decifra um envelope produzido por :meth:`selar`.

        Levanta :class:`ErroDeCriptografia` se o envelope estiver corrompido, se o
        `aad` não corresponder ou se a chave não for a mesma.
        """
        if not envelope or len(envelope) <= len(VERSAO_ENVELOPE) + TAMANHO_NONCE:
            raise ErroDeCriptografia("envelope vazio ou truncado")
        versao = envelope[: len(VERSAO_ENVELOPE)]
        if versao != VERSAO_ENVELOPE:
            raise ErroDeCriptografia(f"versão de envelope desconhecida: {versao!r}")
        inicio = len(VERSAO_ENVELOPE)
        nonce = envelope[inicio : inicio + TAMANHO_NONCE]
        cifrado = envelope[inicio + TAMANHO_NONCE :]
        try:
            return AESGCM(self.chave).decrypt(nonce, cifrado, aad or None)
        except InvalidTag as exc:
            raise ErroDeCriptografia(
                "não foi possível abrir o envelope: chave errada, dados corrompidos "
                "ou contexto (aad) incompatível"
            ) from exc


def aad_do_tenant(tenant_id: object) -> bytes:
    """Contexto padrão de selagem por tenant.

    Impede que um envelope de um tenant seja lido no contexto de outro.
    """
    return f"tenant:{tenant_id}".encode()
