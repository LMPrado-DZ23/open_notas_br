"""Guarda contra mock em produção (regra 11 / P4).

Um dublê ativo em produção não falha: responde sucesso com dado inventado. Num
sistema fiscal esse é o pior modo de falha — nota com aparência de autorizada e
nenhum documento real.
"""

from __future__ import annotations

import base64

import pytest
from app.core.config import Settings, validar_ambiente_de_execucao

CHAVE = base64.b64encode(b"k" * 32).decode()


class TestMockEmProducao:
    def test_recusa_mock_em_producao(self) -> None:
        # A checagem e de STARTUP, nao do construtor: ler Settings para inspecao nao pode
        # explodir (era o que quebrava o CI, que define NFSE_ADAPTER=mock no ambiente).
        conf = Settings(environment="production", nfse_adapter="mock", master_encryption_key=CHAVE)
        with pytest.raises(ValueError, match="NFSE_ADAPTER=mock"):
            validar_ambiente_de_execucao(conf)

    def test_construir_settings_com_mock_em_producao_nao_explode(self) -> None:
        conf = Settings(environment="production", nfse_adapter="mock", master_encryption_key=CHAVE)
        assert conf.nfse_adapter == "mock"

    def test_producao_com_sefin_passa(self) -> None:
        conf = Settings(environment="production", nfse_adapter="sefin", master_encryption_key=CHAVE)
        assert conf.nfse_adapter == "sefin"

    def test_teste_com_mock_passa(self) -> None:
        assert Settings(environment="test", nfse_adapter="mock").nfse_adapter == "mock"

    def test_desenvolvimento_com_mock_passa(self) -> None:
        assert Settings(environment="development", nfse_adapter="mock").nfse_adapter == "mock"

    def test_staging_com_mock_passa(self) -> None:
        # Só produção bloqueia: em staging o dublê é legítimo.
        assert Settings(environment="staging", nfse_adapter="mock").nfse_adapter == "mock"
