"""Servico de CEP: cache em Redis na frente das fontes publicas."""

from __future__ import annotations

import json
import logging

from app.cep.client import (
    TTL_ACERTO,
    TTL_NAO_ENCONTRADO,
    CepInvalido,
    CepNaoEncontrado,
    Endereco,
    FonteIndisponivel,
    consultar,
    normalizar,
)

logger = logging.getLogger(__name__)

PREFIXO = "cep:"


class ServicoCep:
    """Consulta CEP com cache. Falha de cache nao derruba a consulta."""

    def __init__(self, redis=None) -> None:
        self._redis = redis

    async def _ler_cache(self, chave: str):
        if self._redis is None:
            return None
        try:
            bruto = await self._redis.get(chave)
        except Exception:
            logger.warning("cache_cep_leitura_falhou", exc_info=True)
            return None
        if not bruto:
            return None
        try:
            return json.loads(bruto)
        except ValueError:
            return None

    async def _gravar(self, chave: str, valor, ttl: int) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(chave, json.dumps(valor, ensure_ascii=False), ex=ttl)
        except Exception:
            logger.warning("cache_cep_gravacao_falhou", exc_info=True)

    async def buscar(self, cep: str) -> Endereco:
        normalizado = normalizar(cep)
        chave = f"{PREFIXO}{normalizado}"

        em_cache = await self._ler_cache(chave)
        if em_cache is not None:
            return Endereco(**em_cache)

        try:
            endereco = await consultar(normalizado)
        except CepNaoEncontrado:
            # Guardar o "nao existe" evita martelar a fonte a cada tecla, e o TTL
            # curto garante que corrigir o CEP apareca rapido.
            await self._gravar(chave, {"nao_encontrado": True}, TTL_NAO_ENCONTRADO)
            raise

        await self._gravar(chave, endereco.para_dict(), TTL_ACERTO)
        return endereco


__all__ = [
    "CepInvalido",
    "CepNaoEncontrado",
    "Endereco",
    "FonteIndisponivel",
    "ServicoCep",
]
