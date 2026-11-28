"""Rota de CEP: 422 (formato), 404 (não existe) e 503 (fontes fora).

Os três códigos existem porque a ação do checkout muda em cada caso: corrigir o campo, pedir o endereço
manualmente ou simplesmente tentar de novo em instantes. Confundir 404 com 503 faz o cliente achar que
o CEP está errado quando as fontes é que caíram.
"""

from __future__ import annotations

import pytest
from app.api.v1 import consulta as rota
from app.cep.service import CepInvalido, CepNaoEncontrado, Endereco, FonteIndisponivel
from fastapi import HTTPException


class ServicoFalso:
    def __init__(self, resultado=None, erro: Exception | None = None) -> None:
        self._resultado = resultado
        self._erro = erro

    async def buscar(self, cep: str):
        if self._erro is not None:
            raise self._erro
        return self._resultado


def _endereco() -> Endereco:
    return Endereco(
        cep="72900000",
        logradouro="Rua A",
        complemento=None,
        bairro="Centro",
        municipio="Aguas Lindas de Goias",
        uf="GO",
        codigo_ibge="5200258",
        fonte="viacep",
    )


def _montar(monkeypatch, servico) -> None:
    monkeypatch.setattr(rota, "ServicoCep", lambda redis: servico)
    monkeypatch.setattr(rota, "obter_redis", lambda: object())


class TestConsultaCep:
    async def test_sucesso_devolve_endereco_com_ibge(self, monkeypatch) -> None:
        _montar(monkeypatch, ServicoFalso(_endereco()))

        saida = await rota.consultar_cep("72900-000")

        assert saida.cep == "72900000"
        assert saida.codigo_ibge == "5200258"

    async def test_formato_invalido_vira_422(self, monkeypatch) -> None:
        _montar(monkeypatch, ServicoFalso(erro=CepInvalido("CEP deve ter 8 dígitos")))

        with pytest.raises(HTTPException) as erro:
            await rota.consultar_cep("729")

        assert erro.value.status_code == 422

    async def test_nao_encontrado_vira_404(self, monkeypatch) -> None:
        _montar(monkeypatch, ServicoFalso(erro=CepNaoEncontrado("CEP não encontrado")))

        with pytest.raises(HTTPException) as erro:
            await rota.consultar_cep("99999999")

        assert erro.value.status_code == 404

    async def test_fontes_fora_vira_503(self, monkeypatch) -> None:
        _montar(monkeypatch, ServicoFalso(erro=FonteIndisponivel("todas as fontes caíram")))

        with pytest.raises(HTTPException) as erro:
            await rota.consultar_cep("72900000")

        assert erro.value.status_code == 503
