"""Testes de consulta de CNPJ: clientes, cache e degradação.

Nenhum teste toca a rede: `httpx.MockTransport` devolve a resposta que o teste
define. O comportamento real das fontes públicas foi verificado à parte, por
chamada de verdade, e está registrado em `docs/REFERENCIAS.md` (seção 8).
"""

from __future__ import annotations

import json

import httpx
import pytest
from app.cnpj.client import (
    BrasilApiCnpj,
    CnpjInvalido,
    CnpjNaoEncontrado,
    DadosCnpj,
    FonteIndisponivel,
    MinhaReceitaCnpj,
    SerproCnpj,
    validar_entrada,
)
from app.cnpj.service import ServicoCnpj

CNPJ = "33000167000101"

PAYLOAD_BRASILAPI = {
    "cnpj": "33.000.167/0001-01",
    "razao_social": "PETROLEO BRASILEIRO S A PETROBRAS",
    "nome_fantasia": "PETROBRAS",
    "situacao_cadastral": 2,
    "descricao_situacao_cadastral": "ATIVA",
    "uf": "RJ",
    "municipio": "RIO DE JANEIRO",
    "codigo_municipio_ibge": 3304557,
    "cnae_fiscal": 600001,
    "cnae_fiscal_descricao": "Extração de petróleo",
    "natureza_juridica": "Sociedade anônima fechada",
    "data_inicio_atividade": "1953-10-03",
    "opcao_pelo_simples": False,
    "opcao_pelo_mei": False,
    "email": None,
    "ddd_telefone_1": "2125344477",
}


def transporte(status: int, corpo: object) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(corpo, str):
            return httpx.Response(status, text=corpo)
        return httpx.Response(status, json=corpo)

    return httpx.MockTransport(handler)


class TestValidacao:
    def test_aceita_cnpj_valido(self) -> None:
        assert validar_entrada("33.000.167/0001-01") == CNPJ

    def test_rejeita_dv_errado(self) -> None:
        with pytest.raises(CnpjInvalido, match="dígito"):
            validar_entrada("33000167000102")

    def test_rejeita_tamanho(self) -> None:
        with pytest.raises(CnpjInvalido, match="14"):
            validar_entrada("123")

    def test_aceita_alfanumerico(self) -> None:
        assert validar_entrada("12.ABC.345/01DE-35") == "12ABC34501DE35"


class TestBrasilApi:
    async def test_normaliza_resposta(self) -> None:
        cliente = BrasilApiCnpj(transport=transporte(200, PAYLOAD_BRASILAPI))
        dados = await cliente.consultar(CNPJ)

        assert dados.razao_social == "PETROLEO BRASILEIRO S A PETROBRAS"
        assert dados.uf == "RJ"
        assert dados.codigo_municipio_ibge == "3304557"
        assert dados.cnae_fiscal == "600001"
        assert dados.opcao_simples is False
        assert dados.telefone == "2125344477"
        assert dados.fonte == "brasilapi"

    async def test_404_vira_nao_encontrado(self) -> None:
        cliente = BrasilApiCnpj(transport=transporte(404, {"message": "não encontrado"}))
        with pytest.raises(CnpjNaoEncontrado):
            await cliente.consultar(CNPJ)

    async def test_500_vira_indisponivel(self) -> None:
        cliente = BrasilApiCnpj(transport=transporte(500, "erro"))
        with pytest.raises(FonteIndisponivel, match="indisponível"):
            await cliente.consultar(CNPJ)

    async def test_429_vira_indisponivel(self) -> None:
        cliente = BrasilApiCnpj(transport=transporte(429, "limite"))
        with pytest.raises(FonteIndisponivel, match="limite"):
            await cliente.consultar(CNPJ)

    async def test_url_monta_com_cnpj_normalizado(self) -> None:
        capturado: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            capturado["url"] = str(request.url)
            return httpx.Response(200, json=PAYLOAD_BRASILAPI)

        cliente = BrasilApiCnpj(transport=httpx.MockTransport(handler))
        await cliente.consultar("33.000.167/0001-01")
        assert capturado["url"].endswith(f"/{CNPJ}")


class TestMinhaReceita:
    async def test_mesmo_formato_de_campos(self) -> None:
        cliente = MinhaReceitaCnpj(transport=transporte(200, PAYLOAD_BRASILAPI))
        dados = await cliente.consultar(CNPJ)
        assert dados.razao_social.startswith("PETROLEO")
        assert dados.fonte == "minhareceita"


class TestSerpro:
    async def test_sem_token_nao_chama(self) -> None:
        cliente = SerproCnpj(token="")
        with pytest.raises(FonteIndisponivel, match="token"):
            await cliente.consultar(CNPJ)

    async def test_envia_bearer(self) -> None:
        capturado: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            capturado["auth"] = request.headers.get("Authorization", "")
            return httpx.Response(200, json=PAYLOAD_BRASILAPI)

        cliente = SerproCnpj(token="abc123", transport=httpx.MockTransport(handler))
        await cliente.consultar(CNPJ)
        assert capturado["auth"] == "Bearer abc123"


class FakeRedis:
    """Redis mínimo em memória, para testar cache sem subir serviço."""

    def __init__(self) -> None:
        self.dados: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    async def get(self, chave: str) -> str | None:
        return self.dados.get(chave)

    async def set(self, chave: str, valor: str, ex: int | None = None) -> None:
        self.dados[chave] = valor
        if ex:
            self.ttl[chave] = ex

    async def delete(self, chave: str) -> None:
        self.dados.pop(chave, None)


class FonteFalsa:
    """Fonte controlável para testar a cadeia."""

    def __init__(self, nome: str, *, dados: DadosCnpj | None = None, erro: Exception | None = None):
        self.nome = nome
        self._dados = dados
        self._erro = erro
        self.chamadas = 0

    async def consultar(self, cnpj: str) -> DadosCnpj:
        self.chamadas += 1
        if self._erro is not None:
            raise self._erro
        assert self._dados is not None
        return self._dados


def dados(razao: str = "EMPRESA X", fonte: str = "falsa") -> DadosCnpj:
    return DadosCnpj(cnpj=CNPJ, razao_social=razao, fonte=fonte)


class TestServico:
    async def test_usa_cache_na_segunda_chamada(self) -> None:
        fonte = FonteFalsa("f1", dados=dados())
        servico = ServicoCnpj([fonte], redis=FakeRedis())

        primeira = await servico.consultar(CNPJ)
        segunda = await servico.consultar(CNPJ)

        assert primeira.do_cache is False
        assert segunda.do_cache is True
        assert fonte.chamadas == 1
        assert segunda.dados.razao_social == "EMPRESA X"

    async def test_cache_pode_ser_ignorado(self) -> None:
        fonte = FonteFalsa("f1", dados=dados())
        servico = ServicoCnpj([fonte], redis=FakeRedis())

        await servico.consultar(CNPJ)
        await servico.consultar(CNPJ, usar_cache=False)
        assert fonte.chamadas == 2

    async def test_cai_para_segunda_fonte(self) -> None:
        quebrada = FonteFalsa("quebrada", erro=FonteIndisponivel("fora do ar"))
        boa = FonteFalsa("boa", dados=dados("EMPRESA Y"))
        servico = ServicoCnpj([quebrada, boa], redis=FakeRedis())

        resultado = await servico.consultar(CNPJ)
        assert resultado.dados.razao_social == "EMPRESA Y"
        assert resultado.fontes_tentadas == ["quebrada", "boa"]

    async def test_todas_indisponiveis_vira_indisponivel(self) -> None:
        a = FonteFalsa("a", erro=FonteIndisponivel("x"))
        b = FonteFalsa("b", erro=FonteIndisponivel("y"))
        servico = ServicoCnpj([a, b], redis=FakeRedis())

        with pytest.raises(FonteIndisponivel, match="nenhuma fonte"):
            await servico.consultar(CNPJ)

    async def test_nao_encontrado_apos_fontes(self) -> None:
        a = FonteFalsa("a", erro=CnpjNaoEncontrado("nao"))
        servico = ServicoCnpj([a], redis=FakeRedis())

        with pytest.raises(CnpjNaoEncontrado, match="não encontrado"):
            await servico.consultar(CNPJ)

    async def test_alfanumerico_nao_encontrado_explica_formato_novo(self) -> None:
        a = FonteFalsa("a", erro=CnpjNaoEncontrado("nao"))
        servico = ServicoCnpj([a], redis=FakeRedis())

        with pytest.raises(CnpjNaoEncontrado, match="alfanumérico"):
            await servico.consultar("12ABC34501DE35")

    async def test_cache_fora_do_ar_nao_derruba(self) -> None:
        class CacheQuebrado:
            async def get(self, chave: str) -> str | None:
                raise RuntimeError("redis caiu")

            async def set(self, *a, **k) -> None:
                raise RuntimeError("redis caiu")

        fonte = FonteFalsa("f1", dados=dados())
        servico = ServicoCnpj([fonte], redis=CacheQuebrado())

        resultado = await servico.consultar(CNPJ)
        assert resultado.dados.razao_social == "EMPRESA X"

    async def test_sem_redis_funciona(self) -> None:
        fonte = FonteFalsa("f1", dados=dados())
        servico = ServicoCnpj([fonte], redis=None)
        resultado = await servico.consultar(CNPJ)
        assert resultado.do_cache is False

    async def test_cnpj_invalido_nao_gasta_fonte(self) -> None:
        fonte = FonteFalsa("f1", dados=dados())
        servico = ServicoCnpj([fonte], redis=FakeRedis())
        with pytest.raises(CnpjInvalido):
            await servico.consultar("123")
        assert fonte.chamadas == 0

    async def test_cache_serializa_dados(self) -> None:
        redis = FakeRedis()
        fonte = FonteFalsa("f1", dados=dados())
        servico = ServicoCnpj([fonte], redis=redis)

        await servico.consultar(CNPJ)
        bruto = redis.dados[f"cnpj:{CNPJ}"]
        corpo = json.loads(bruto)
        assert corpo["razao_social"] == "EMPRESA X"
        assert corpo["cnpj"] == CNPJ
