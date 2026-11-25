"""Geração e verificação de credenciais: API keys e assinatura de webhook.

Duas garantias centrais:

1. **API key nunca é armazenada em claro.** Guardamos apenas SHA-256 do valor. O
   segredo aparece uma única vez, na resposta da criação.
2. **Comparação em tempo constante** na verificação de assinatura HMAC, para não
   vazar prefixo por diferença de tempo.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

PREFIXO_API_KEY = "nb_"
TAMANHO_TOKEN_BYTES = 32
TAMANHO_PREFIXO_VISIVEL = 8


def gerar_api_key() -> tuple[str, str, str]:
    """Cria uma API key nova.

    Devolve ``(chave_completa, prefixo_visivel, hash_armazenavel)``.

    O prefixo visível serve para o operador identificar a credencial na listagem
    sem que o sistema guarde o segredo.
    """
    segredo = secrets.token_urlsafe(TAMANHO_TOKEN_BYTES)
    completa = f"{PREFIXO_API_KEY}{segredo}"
    prefixo = completa[: len(PREFIXO_API_KEY) + TAMANHO_PREFIXO_VISIVEL]
    return completa, prefixo, hash_api_key(completa)


def hash_api_key(chave: str) -> str:
    """SHA-256 hexadecimal da API key.

    SHA-256 puro (sem salt/custo) é adequado aqui porque a chave tem 256 bits de
    entropia real: não há dicionário que a alcance, diferente de senha humana.
    """
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


def hashs_iguais(a: str, b: str) -> bool:
    """Compara dois hashes em tempo constante."""
    return hmac.compare_digest(a, b)


def assinar_webhook(corpo: bytes, segredo: bytes) -> str:
    """Assinatura HMAC-SHA256 hexadecimal do corpo do webhook.

    O consumidor recalcula com o mesmo segredo e compara em tempo constante.
    """
    return hmac.new(segredo, corpo, hashlib.sha256).hexdigest()


def verificar_assinatura_webhook(corpo: bytes, segredo: bytes, assinatura: str) -> bool:
    """True se `assinatura` corresponde ao HMAC-SHA256 de `corpo`."""
    if not assinatura:
        return False
    esperado = assinar_webhook(corpo, segredo)
    return hmac.compare_digest(esperado, assinatura.strip().lower())


def gerar_segredo_webhook() -> str:
    """Segredo de webhook por tenant (32 bytes em hexadecimal)."""
    return secrets.token_hex(32)
