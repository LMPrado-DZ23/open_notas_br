"""Consulta de CEP: normalização, fontes, fallback e cache.

Os testes não dependem de rede: o transporte HTTP é injetado, então o que se
verifica é o comportamento do nosso código diante do que as fontes respondem.
"""

from __future__ import annotations

import httpx
import pytest
from app.cep.client import (
    CepInvalido,
    CepNaoEncontrado,
    Endereco,
    FonteIndisponivel,
    _de_brasilapi,
    _de_viacep,
    consultar,
    normalizar,
)
from app.cep.service import PREFIXO, ServicoCep

VIACEP_OK = {
    "cep": "01001-000",
    "logradouro": "Praça da Sé",
    "complemento": "lado ímpar",
    "bairro": "Sé",
    "localidade": "São Paulo",
    "uf": "SP",
    "ibge": "3550308",
}
VIACEP_NAO_EXISTE = {"erro": "true"}
BRASILAPI_OK = {
    "cep": "01001000",
    "state": "SP",
    "city": "São Paulo",
    "neighborhood": "Sé",
    "street": "Praça da Sé",
}


class TestNormalizacao:
    @pytest.mark.parametrize("entrada", ["01001000", "01001-000", " 01001000 ", "01001 000"])
    def test_aceita_formatos_comuns(self, entrada: str) -> None:
        assert normalizar(entrada) == "01001000"

    def test_curto_demais(self) -> None:
        with pytest.raises(CepInvalido, match="8 dígitos"):
            normalizar("0100100")

    def test_com_letras(self) -> None:
        with pytest.raises(CepInvalido):
            normalizar("abcdefgh")

    def test_vazio(self) -> None:
        with pytest.raises(CepInvalido):
            normalizar("")


class TestInterpretacao:
    def test_viacep_completo(self) -> None:
        endereco = _de_viacep(VIACEP_OK, "01001000")
        assert endereco is not None
        assert endereco.municipio == "São Paulo"
        assert endereco.codigo_ibge == "3550308"
        assert endereco.fonte == "viacep"

    def test_viacep_nao_encontrado(self) -> None:
        assert _de_viacep(VIACEP_NAO_EXISTE, "01001000") is None

    def test_brasilapi_completo(self) -> None:
        endereco = _de_brasilapi(BRASILAPI_OK, "01001000")
        assert endereco is not None
        assert endereco.uf == "SP"
        assert endereco.fonte == "brasilapi"

    def test_brasilapi_sem_municipio(self) -> None:
        assert _de_brasilapi({}, "01001000") is None


def transporte(respostas: dict[str, httpx.Response]) -> httpx.MockTransport:
    def manipulador(request: httpx.Request) -> httpx.Response:
        for trecho, resposta in respostas.items():
            if trecho in str(request.url):
                return resposta
        return httpx.Response(500, request=request)

    return httpx.MockTransport(manipulador)


class TestConsultar:
    async def test_viacep_responde_e_nao_chama_fallback(self) -> None:
        chamadas: list[str] = []

        def manipulador(request: httpx.Request) -> httpx.Response:
            chamadas.append(str(request.url))
            if "viacep" in str(request.url):
                return httpx.Response(200, json=VIACEP_OK, request=request)
            raise AssertionError("não deveria chamar a BrasilAPI")

        async with httpx.AsyncClient(transport=httpx.MockTransport(manipulador)) as http:
            endereco = await consultar("01001-000", cliente=http)
        assert endereco.fonte == "viacep"
        assert len(chamadas) == 1

    async def test_cai_para_brasilapi_quando_viacep_nao_conhece(self) -> None:
        async with httpx.AsyncClient(
            transport=transporte(
                {
                    "viacep": httpx.Response(200, json=VIACEP_NAO_EXISTE),
                    "brasilapi": httpx.Response(200, json=BRASILAPI_OK),
                }
            )
        ) as http:
            endereco = await consultar("01001000", cliente=http)
        assert endereco.fonte == "brasilapi"

    async def test_cep_inexistente_nas_duas(self) -> None:
        async with httpx.AsyncClient(
            transport=transporte(
                {
                    "viacep": httpx.Response(200, json=VIACEP_NAO_EXISTE),
                    "brasilapi": httpx.Response(404, json={}),
                }
            )
        ) as http:
            with pytest.raises(CepNaoEncontrado):
                await consultar("99999999", cliente=http)

    async def test_duas_fontes_fora_do_ar_nao_afirma_que_cep_nao_existe(self) -> None:
        # Distinção importante: fonte fora do ar não significa CEP inválido.
        async with httpx.AsyncClient(
            transport=transporte(
                {
                    "viacep": httpx.Response(500),
                    "brasilapi": httpx.Response(503),
                }
            )
        ) as http:
            with pytest.raises(FonteIndisponivel, match="manualmente"):
                await consultar("01001000", cliente=http)

    async def test_erro_de_rede_vira_fonte_indisponivel(self) -> None:
        def manipulador(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("sem rede")

        async with httpx.AsyncClient(transport=httpx.MockTransport(manipulador)) as http:
            with pytest.raises(FonteIndisponivel):
                await consultar("01001000", cliente=http)


class RedisFalso:
    def __init__(self) -> None:
        self.dados: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.leituras = 0

    async def get(self, chave: str):
        self.leituras += 1
        return self.dados.get(chave)

    async def set(self, chave: str, valor: str, ex: int | None = None) -> None:
        self.dados[chave] = valor
        if ex:
            self.ttls[chave] = ex


class RedisQuebrado:
    async def get(self, chave: str):
        raise RuntimeError("cache fora")

    async def set(self, *args, **kwargs):
        raise RuntimeError("cache fora")


class TestServico:
    async def test_segunda_consulta_vem_do_cache(self, monkeypatch) -> None:
        chamadas = {"n": 0}

        async def falso(cep: str, *, cliente=None) -> Endereco:
            chamadas["n"] += 1
            return _de_viacep(VIACEP_OK, cep)

        monkeypatch.setattr("app.cep.service.consultar", falso)
        redis = RedisFalso()
        servico = ServicoCep(redis)

        primeiro = await servico.buscar("01001000")
        segundo = await servico.buscar("01001-000")
        assert chamadas["n"] == 1, "segunda consulta deve sair do cache"
        assert primeiro.municipio == segundo.municipio
        assert redis.ttls[f"{PREFIXO}01001000"] > 0

    async def test_cache_de_nao_encontrado_tem_ttl_curto(self, monkeypatch) -> None:
        async def falso(cep: str, *, cliente=None) -> Endereco:
            raise CepNaoEncontrado("nao existe")

        monkeypatch.setattr("app.cep.service.consultar", falso)
        redis = RedisFalso()
        servico = ServicoCep(redis)
        with pytest.raises(CepNaoEncontrado):
            await servico.buscar("99999999")
        assert redis.ttls[f"{PREFIXO}99999999"] <= 300

    async def test_cache_fora_do_ar_nao_derruba_a_consulta(self, monkeypatch) -> None:
        # Sem monkeypatch este teste falaria a rede: teste de unidade não pode
        # depender de serviço público para passar (CI ficaria instável).
        async def falso(cep: str, *, cliente=None) -> Endereco:
            return _de_viacep(VIACEP_OK, cep)

        monkeypatch.setattr("app.cep.service.consultar", falso)
        servico = ServicoCep(RedisQuebrado())
        endereco = await servico.buscar("01001000")
        assert endereco.municipio == "São Paulo"

    async def test_sem_redis_funciona(self, monkeypatch) -> None:
        async def falso(cep: str, *, cliente=None) -> Endereco:
            return _de_viacep(VIACEP_OK, cep)

        monkeypatch.setattr("app.cep.service.consultar", falso)
        servico = ServicoCep(None)
        endereco = await servico.buscar("01001000")
        assert endereco.uf == "SP"
