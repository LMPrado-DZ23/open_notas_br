"""Guarda contra mock em produção (regra 11 / P4).

Um dublê ativo em produção não falha: responde sucesso com dado inventado. Num
sistema fiscal esse é o pior modo de falha — nota com aparência de autorizada e
nenhum documento real.
"""

from __future__ import annotations

import base64

import pytest
from app.core.config import Settings
from pydantic import ValidationError

CHAVE = base64.b64encode(b"k" * 32).decode()


class TestMockEmProducao:
    def test_recusa_mock_em_producao(self) -> None:
        with pytest.raises(ValidationError, match="NFSE_ADAPTER=mock"):
            Settings(
                environment="production",
                nfse_adapter="mock",
                master_encryption_key=CHAVE,
            )

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
