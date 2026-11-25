"""Orquestração da consulta de CNPJ: cache, limite e degradação graciosa.

Ordem de tentativa: cache → fontes na ordem configurada. O resultado positivo é
cacheado; "não encontrado" **não** é cacheado por muito tempo, porque cadastro
novo passa a existir.

Degradação graciosa é requisito, não detalhe: se a fonte cair, a resposta é
"indisponível, tente depois" — nunca erro 500 nem "CNPJ inválido". E se todas as
fontes desconhecerem um CNPJ alfanumérico, a mensagem diz que a fonte pode ainda
não cobrir o formato novo.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.cnpj.client import (
    CnpjInvalido,
    CnpjNaoEncontrado,
    ConsultaCnpj,
    DadosCnpj,
    FonteIndisponivel,
    eh_alfanumerico,
    validar_entrada,
)

logger = logging.getLogger(__name__)

CHAVE_CACHE = "cnpj:{cnpj}"
TTL_NAO_ENCONTRADO_SEGUNDOS = 300


@dataclass(slots=True)
class ResultadoConsulta:
    """Resultado com a procedência da informação."""

    dados: DadosCnpj
    do_cache: bool
    fontes_tentadas: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.dados.to_dict(),
            "do_cache": self.do_cache,
            "fontes_tentadas": self.fontes_tentadas,
        }


class ServicoCnpj:
    """Consulta CNPJ com cache Redis e cadeia de fontes."""

    def __init__(
        self,
        fontes: list[ConsultaCnpj],
        *,
        redis: Any = None,
        ttl_segundos: int = 86_400,
    ) -> None:
        self.fontes = fontes
        self.redis = redis
        self.ttl_segundos = ttl_segundos

    # -- cache ---------------------------------------------------------
    async def _ler_cache(self, cnpj: str) -> DadosCnpj | None:
        if self.redis is None:
            return None
        try:
            bruto = await self.redis.get(CHAVE_CACHE.format(cnpj=cnpj))
        except Exception as exc:
            logger.warning("cache_cnpj_leitura_falhou", extra={"erro": str(exc)})
            return None
        if not bruto:
            return None
        try:
            dados = json.loads(bruto)
        except ValueError:
            return None
        return DadosCnpj(**dados)

    async def _gravar_cache(self, dados: DadosCnpj, *, ttl: int | None = None) -> None:
        if self.redis is None:
            return
        try:
            await self.redis.set(
                CHAVE_CACHE.format(cnpj=dados.cnpj),
                json.dumps(dados.to_dict(), ensure_ascii=False),
                ex=ttl or self.ttl_segundos,
            )
        except Exception as exc:
            logger.warning("cache_cnpj_escrita_falhou", extra={"erro": str(exc)})

    async def invalidar(self, cnpj: str) -> None:
        """Remove do cache (útil após atualização cadastral)."""
        if self.redis is None:
            return
        try:
            await self.redis.delete(CHAVE_CACHE.format(cnpj=validar_entrada(cnpj)))
        except Exception:
            logger.warning("cache_cnpj_invalidacao_falhou")

    # -- consulta ------------------------------------------------------
    async def consultar(self, cnpj: str, *, usar_cache: bool = True) -> ResultadoConsulta:
        """Consulta o CNPJ, preferindo cache e caindo para as fontes."""
        try:
            normalizado = validar_entrada(cnpj)
        except CnpjInvalido:
            raise

        if usar_cache:
            em_cache = await self._ler_cache(normalizado)
            if em_cache is not None:
                logger.info("cnpj_cache_hit", extra={"cnpj": normalizado})
                return ResultadoConsulta(em_cache, True, [])

        tentadas: list[str] = []
        indisponiveis: list[str] = []
        nao_encontrados: list[str] = []

        for fonte in self.fontes:
            tentadas.append(fonte.nome)
            try:
                dados = await fonte.consultar(normalizado)
            except CnpjNaoEncontrado:
                nao_encontrados.append(fonte.nome)
                logger.info("cnpj_nao_encontrado", extra={"cnpj": normalizado, "fonte": fonte.nome})
                continue
            except FonteIndisponivel as exc:
                indisponiveis.append(f"{fonte.nome}: {exc}")
                logger.warning(
                    "cnpj_fonte_indisponivel",
                    extra={"cnpj": normalizado, "fonte": fonte.nome, "erro": str(exc)},
                )
                continue

            await self._gravar_cache(dados)
            return ResultadoConsulta(dados, False, tentadas)

        # Nenhuma fonte devolveu dados: decidir entre "não existe" e "não deu".
        if nao_encontrados:
            await self._gravar_cache(
                DadosCnpj(cnpj=normalizado, fonte="nenhuma", descricao_situacao="nao_encontrado"),
                ttl=TTL_NAO_ENCONTRADO_SEGUNDOS,
            )
            detalhe = (
                " As fontes públicas consultadas podem ainda não cobrir CNPJ alfanumérico."
                if eh_alfanumerico(normalizado)
                else ""
            )
            raise CnpjNaoEncontrado(
                f"CNPJ {normalizado} não encontrado nas fontes consultadas "
                f"({', '.join(nao_encontrados)}).{detalhe}"
            )

        raise FonteIndisponivel(
            "nenhuma fonte de CNPJ respondeu; tente novamente em instantes"
            + (f" ({'; '.join(indisponiveis)})" if indisponiveis else "")
        )

    async def consultar_com_fallback_local(
        self, cnpj: str, *, base_local: Any = None
    ) -> ResultadoConsulta:
        """Consulta e, se todas as fontes caírem, tenta a base aberta local.

        A base da RFB (`rfb-cnpj`) é o último recurso: não depende de rede nem de
        cota. Fica atrás de uma interface para que a integração real entre na
        Fase 3 sem reescrever o serviço.
        """
        try:
            return await self.consultar(cnpj)
        except FonteIndisponivel:
            if base_local is None:
                raise
            logger.warning("cnpj_usando_base_local", extra={"cnpj": cnpj})
            dados = await base_local.consultar(cnpj)
            return ResultadoConsulta(dados, False, ["base_local"])
