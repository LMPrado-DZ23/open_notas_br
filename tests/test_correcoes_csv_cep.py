"""Dois defeitos que os testes de cobertura revelaram e que foram corrigidos aqui.

1. `app/batches/csv.py`: `_validar` só era chamada quando a linha tinha `idempotency_key`, então linha
   **sem** chave passava como válida e ia para o banco com chave vazia — todas colidindo na busca de
   idempotência. O efeito prático é um lote onde "uma linha deu certo, o resto já existe".
2. `app/cep/service.py`: o "não existe" é cacheado como `{"nao_encontrado": True}` e o cache era passado
   direto para `Endereco(**...)` — `TypeError` e **500** na segunda consulta do mesmo CEP, em vez de 404.
"""

from __future__ import annotations

import json

import pytest
from app.batches.csv import ler_csv
from app.cep.service import CepNaoEncontrado, Endereco, ServicoCep

CABECALHO = "idempotency_key,valor,descricao,competencia\n"


class RedisFalso:
    def __init__(self) -> None:
        self.dados: dict[str, str] = {}
        self.gravados: list[tuple[str, int]] = []

    async def get(self, chave: str):
        return self.dados.get(chave)

    async def set(self, chave: str, valor: str, ex: int | None = None) -> None:
        self.dados[chave] = valor
        self.gravados.append((chave, ex or 0))


class TestLoteSemChave:
    def test_linha_sem_idempotency_key_e_recusada_na_leitura(self) -> None:
        """Antes passava como válida: o lote gravava chave vazia e colidia na idempotência."""
        lote = ler_csv((CABECALHO + ",100.00,servico,2026-11\n").encode())

        assert lote.linhas[0].erro == "idempotency_key vazia"

    def test_linha_com_chave_curta_e_recusada(self) -> None:
        lote = ler_csv((CABECALHO + "abc,100.00,servico,2026-11\n").encode())

        assert "ao menos 8 caracteres" in lote.linhas[0].erro

    def test_linha_valida_continua_valida(self) -> None:
        lote = ler_csv((CABECALHO + "chave-boa-123,100.00,servico,2026-11\n").encode())

        assert lote.linhas[0].erro is None


class TestCepNegativoEmCache:
    async def test_segunda_consulta_de_cep_inexistente_da_404_e_nao_500(self, monkeypatch) -> None:
        from app.cep import service as modulo

        chamadas: list[str] = []

        async def consultar(cep: str):
            chamadas.append(cep)
            raise CepNaoEncontrado(f"CEP {cep} não encontrado")

        monkeypatch.setattr(modulo, "consultar", consultar)
        redis = RedisFalso()
        servico = ServicoCep(redis)

        with pytest.raises(CepNaoEncontrado):
            await servico.buscar("99999999")

        assert json.loads(redis.dados["cep:99999999"]) == {"nao_encontrado": True}

        # Segunda consulta: vem do cache negativo, com 404 — e sem martelar a fonte.
        with pytest.raises(CepNaoEncontrado):
            await servico.buscar("99999999")

        assert chamadas == ["99999999"], "a segunda consulta não pode ir à fonte"

    async def test_cache_de_acerto_continua_devolvendo_endereco(self, monkeypatch) -> None:
        from app.cep import service as modulo

        async def consultar(cep: str):
            return Endereco(
                cep=cep,
                logradouro="Rua A",
                complemento=None,
                bairro="Centro",
                municipio="Goiânia",
                uf="GO",
                codigo_ibge="5208707",
                fonte="viacep",
            )

        monkeypatch.setattr(modulo, "consultar", consultar)
        servico = ServicoCep(RedisFalso())

        primeiro = await servico.buscar("72900000")
        segundo = await servico.buscar("72900000")

        assert primeiro.codigo_ibge == segundo.codigo_ibge == "5208707"
