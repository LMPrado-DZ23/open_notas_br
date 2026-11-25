"""Assinatura HMAC-SHA256 de webhook, com proteção de replay.

Formato do cabeçalho, no estilo consagrado por outros provedores:

    X-Notasbr-Signature: t=1732636800,v1=<hmac_hex>

O que é assinado é ``"{t}.{corpo}"`` — o timestamp entra na mensagem assinada. Sem
isso, um corpo válido capturado pode ser reenviado para sempre: a assinatura
continuaria correta. O receptor precisa rejeitar ``t`` fora da tolerância (padrão
5 minutos), e é isso que `verificar` faz.

[INFERIDO] O formato do cabeçalho é convenção nossa (inspirada em provedores de
pagamento), não norma. Quem integra recebe esta especificação, não uma suposição.
"""

from __future__ import annotations

import hashlib
import hmac
import time

CABECALHO_ASSINATURA = "X-Notasbr-Signature"
CABECALHO_EVENTO = "X-Notasbr-Event"
CABECALHO_ID = "X-Notasbr-Delivery"
TOLERANCIA_SEGUNDOS = 300


class AssinaturaInvalida(Exception):
    """Assinatura ausente, malformada, expirada ou incorreta."""


def assinar(segredo: bytes, corpo: bytes, *, timestamp: int) -> str:
    """HMAC-SHA256 hexadecimal de ``timestamp.corpo``."""
    mensagem = f"{timestamp}.".encode("ascii") + corpo
    return hmac.new(segredo, mensagem, hashlib.sha256).hexdigest()


def cabecalhos(
    segredo: bytes,
    corpo: bytes,
    *,
    evento: str,
    entrega_id: str,
    timestamp: int | None = None,
) -> dict[str, str]:
    """Cabeçalhos completos da requisição de webhook."""
    momento = int(time.time()) if timestamp is None else timestamp
    return {
        CABECALHO_ASSINATURA: f"t={momento},v1={assinar(segredo, corpo, timestamp=momento)}",
        CABECALHO_EVENTO: evento,
        CABECALHO_ID: entrega_id,
        "Content-Type": "application/json",
        "User-Agent": "open_notas_br-webhook/1",
    }


def _extrair(cabecalho: str) -> tuple[int, str]:
    partes: dict[str, str] = {}
    for item in cabecalho.split(","):
        if "=" not in item:
            continue
        chave, valor = item.split("=", 1)
        partes[chave.strip()] = valor.strip()
    if "t" not in partes or "v1" not in partes:
        raise AssinaturaInvalida("cabeçalho de assinatura sem t ou v1")
    try:
        return int(partes["t"]), partes["v1"]
    except ValueError as exc:
        raise AssinaturaInvalida("timestamp da assinatura não é inteiro") from exc


def verificar(
    segredo: bytes,
    corpo: bytes,
    cabecalho: str,
    *,
    agora: int | None = None,
    tolerancia: int = TOLERANCIA_SEGUNDOS,
) -> None:
    """Valida a assinatura; levanta :class:`AssinaturaInvalida` se não conferir.

    Comparação em tempo constante (`hmac.compare_digest`): comparar com `==` vaza
    o prefixo correto pelo tempo de resposta e permite forjar assinatura byte a
    byte.
    """
    momento, recebida = _extrair(cabecalho)
    atual = int(time.time()) if agora is None else agora
    if abs(atual - momento) > tolerancia:
        raise AssinaturaInvalida(
            f"assinatura fora da tolerância de {tolerancia}s "
            f"(t={momento}, agora={atual}) — possível replay"
        )

    esperada = assinar(segredo, corpo, timestamp=momento)
    if not hmac.compare_digest(esperada, recebida):
        raise AssinaturaInvalida("assinatura não confere")


def gerar_segredo() -> str:
    """Segredo novo para um tenant (32 bytes em hexadecimal)."""
    import secrets

    return secrets.token_hex(32)
