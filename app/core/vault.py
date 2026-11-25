"""Fábrica do cofre a partir da configuração.

Existe para que o resto do código não precise saber de onde vem a chave-mestra, e
para que os testes possam injetar uma chave conhecida sem tocar em `Settings`.
"""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.core.crypto import Cofre, ErroDeCriptografia


def obter_cofre(settings: Settings | None = None) -> Cofre:
    """Cofre configurado com a chave-mestra do ambiente.

    Levanta `ValueError` (de `Settings.master_key`) se a chave estiver ausente em
    produção ou malformada — falha alto, na inicialização, e não no meio de uma
    emissão fiscal.
    """
    conf = settings or get_settings()
    return Cofre(conf.master_key())


def selar(conteudo: bytes, *, aad: bytes = b"", settings: Settings | None = None) -> bytes:
    return obter_cofre(settings).selar(conteudo, aad=aad)


def abrir(envelope: bytes, *, aad: bytes = b"", settings: Settings | None = None) -> bytes:
    return obter_cofre(settings).abrir(envelope, aad=aad)


__all__ = ["Cofre", "ErroDeCriptografia", "abrir", "obter_cofre", "selar"]
