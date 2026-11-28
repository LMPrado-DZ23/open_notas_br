"""Consulta de CNPJ: cache, cadeia de fontes e a diferença entre "não existe" e "não deu".

Três desfechos com ações diferentes para o cliente:

- **cache hit**: não gasta cota de fonte;
- **não encontrado**: 404 — CNPJ válido que as fontes não conhecem (com nota sobre alfanumérico);
- **fontes fora**: 503 — transitório, vale retentar.

Confundir os dois últimos faz o cliente "corrigir" um dado que está certo ou desistir de um retry que
funcionaria.
"""

from __future__ import annotations

import json

import pytest
from app.cnpj.client import (
    CnpjInvalido,
    CnpjNaoEncontrado,
    DadosCnpj,
    FonteIndisponivel,
)
from app.cnpj.service import TTL_NAO_ENCONTRADO_SEGUNDOS, ServicoCnpj

CNPJ = "11222333000181"


class FonteFalsa:
    def __init__(self, nome: str, dados=None, erro: Exception | None = None) -> None:
        self.nome = nome
        self._dados = dados
        self._erro = erro
        self.chamadas = 0

    async def consultar(self, cnpj: str):
        self.chamadas += 1
        if self._erro is not None:
            raise self._erro
        return self._dados


class RedisFalso:
    def __init__(self, valor: bytes | None = None, erro: Exception | None = None) -> None:
        self._valor = valor
        self._erro = erro
        self.gravados: list[tuple[str, str, int | None]] = []
        self.apagados: list[str] = []

    async def get(self, chave: str):
        if self._erro is not None:
            raise self._erro
        return self._valor

    async def set(self, chave: str, valor: str, ex: int | None = None) -> None:
        if self._erro is not None:
            raise self._erro
        self.gravados.append((chave, valor, ex))

    async def delete(self, chave: str) -> None:
        if self._erro is not None:
            raise self._erro
        self.apagados.append(chave)


def _dados(**extra) -> DadosCnpj:
    base = dict(cnpj=CNPJ, fonte="teste", razao_social="ACME")
    base.update(extra)
    return DadosCnpj(**base)


class TestCache:
    async def test_sem_redis_nao_le(self) -> None:
        servico = ServicoCnpj([FonteFalsa("f", _dados())], redis=None)

        assert await servico._ler_cache(CNPJ) is None

    async def test_leitura_com_erro_devolve_none(self) -> None:
        servico = ServicoCnpj([], redis=RedisFalso(erro=ConnectionError("fora")))

        assert await servico._ler_cache(CNPJ) is None

    async def test_json_invalido_devolve_none(self) -> None:
        servico = ServicoCnpj([], redis=RedisFalso(valor=b"{nao-e-json"))

        assert await servico._ler_cache(CNPJ) is None

    async def test_hit_evita_as_fontes(self) -> None:
        fonte = FonteFalsa("f", _dados())
        payload = json.dumps(_dados().to_dict()).encode()
        servico = ServicoCnpj([fonte], redis=RedisFalso(valor=payload))

        resultado = await servico.consultar(CNPJ)

        assert resultado.do_cache is True
        assert resultado.fontes_tentadas == []
        assert fonte.chamadas == 0

    async def test_escrita_com_erro_nao_derruba(self) -> None:
        servico = ServicoCnpj([], redis=RedisFalso(erro=ConnectionError("fora")))

        await servico._gravar_cache(_dados())

    async def test_invalidar_sem_redis_e_noop(self) -> None:
        servico = ServicoCnpj([], redis=None)

        await servico.invalidar(CNPJ)

    async def test_invalidar_apaga_chave(self) -> None:
        redis = RedisFalso()
        servico = ServicoCnpj([], redis=redis)

        await servico.invalidar(CNPJ)

        assert redis.apagados == [f"cnpj:{CNPJ}"]

    async def test_invalidar_com_cnpj_invalido_nao_explode(self) -> None:
        """`invalidar` engole o erro de validação: limpar cache não é operação de negócio."""
        servico = ServicoCnpj([], redis=RedisFalso())

        await servico.invalidar("123")


class TestConsulta:
    async def test_cnpj_invalido_propaga(self) -> None:
        servico = ServicoCnpj([FonteFalsa("f", _dados())])

        with pytest.raises(CnpjInvalido):
            await servico.consultar("123")

    async def test_cadeia_cai_para_a_segunda_fonte(self) -> None:
        quebrada = FonteFalsa("a", erro=FonteIndisponivel("sem rede"))
        boa = FonteFalsa("b", _dados())
        servico = ServicoCnpj([quebrada, boa])

        resultado = await servico.consultar(CNPJ)

        assert resultado.dados.razao_social == "ACME"
        assert resultado.fontes_tentadas == ["a", "b"]

    async def test_nao_encontrado_grava_cache_curto_e_levanta(self) -> None:
        redis = RedisFalso()
        servico = ServicoCnpj([FonteFalsa("a", erro=CnpjNaoEncontrado("não achei"))], redis=redis)

        with pytest.raises(CnpjNaoEncontrado) as erro:
            await servico.consultar(CNPJ)

        assert redis.gravados[0][2] == TTL_NAO_ENCONTRADO_SEGUNDOS
        assert "não encontrado nas fontes" in str(erro.value)

    async def test_todas_indisponiveis_levanta_fonte_indisponivel(self) -> None:
        servico = ServicoCnpj(
            [
                FonteFalsa("a", erro=FonteIndisponivel("sem rede")),
                FonteFalsa("b", erro=FonteIndisponivel("cota")),
            ]
        )

        with pytest.raises(FonteIndisponivel) as erro:
            await servico.consultar(CNPJ)

        assert "nenhuma fonte" in str(erro.value)
        assert "sem rede" in str(erro.value)


class TestFallbackLocal:
    async def test_sem_base_local_propaga_o_erro(self) -> None:
        servico = ServicoCnpj([FonteFalsa("a", erro=FonteIndisponivel("sem rede"))])

        with pytest.raises(FonteIndisponivel):
            await servico.consultar_com_fallback_local(CNPJ)

    async def test_com_base_local_usa_ultimo_recurso(self) -> None:
        class BaseLocal:
            async def consultar(self, cnpj):
                return _dados(fonte="base_local")

        servico = ServicoCnpj([FonteFalsa("a", erro=FonteIndisponivel("sem rede"))])

        resultado = await servico.consultar_com_fallback_local(CNPJ, base_local=BaseLocal())

        assert resultado.dados.fonte == "base_local"
        assert resultado.fontes_tentadas == ["base_local"]

    async def test_resultado_vira_dict_com_procedencia(self) -> None:
        """`to_dict` precisa expor de onde veio o dado: cache e fontes tentadas."""
        servico = ServicoCnpj([FonteFalsa("a", _dados())])

        resultado = await servico.consultar(CNPJ)
        corpo = resultado.to_dict()

        assert corpo["do_cache"] is False
        assert corpo["fontes_tentadas"] == ["a"]
        assert corpo["cnpj"] == CNPJ
