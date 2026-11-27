"""Testes da configuração e da política de chave-mestra."""

from __future__ import annotations

import base64
from decimal import Decimal

import pytest
from app.core.config import Settings


def chave_b64(bytes_: bytes = b"\x01" * 32) -> str:
    return base64.b64encode(bytes_).decode()


class TestChaveMestra:
    def test_base64_valido_de_32_bytes(self) -> None:
        settings = Settings(environment="development", master_encryption_key=chave_b64())
        assert settings.master_key() == b"\x01" * 32

    def test_desenvolvimento_sem_chave_deriva_chave_estavel(self) -> None:
        """Sem chave no ambiente, a chave é determinística — e isso é deliberado.

        API e worker são processos separados: com chave efêmera por processo, a API sela o
        segredo e o worker não consegue abrir (`InvalidTag`). Por isso é constante derivada,
        não sorteada. Não há `reset_ephemeral_key`: não existe chave efêmera para descartar.
        """
        settings = Settings(environment="development", master_encryption_key="")

        primeira = settings.master_key()
        segunda = settings.master_key()

        assert len(primeira) == 32
        assert primeira == segunda, "a chave de desenvolvimento deve ser estável dentro do processo"

    def test_producao_sem_chave_falha(self) -> None:
        settings = Settings(environment="production", master_encryption_key="")
        with pytest.raises(ValueError, match="obrigatória"):
            settings.master_key()

    def test_base64_invalido_falha(self) -> None:
        settings = Settings(environment="development", master_encryption_key="não-é-base64!!")
        with pytest.raises(ValueError, match="base64"):
            settings.master_key()

    def test_tamanho_errado_falha(self) -> None:
        settings = Settings(
            environment="development", master_encryption_key=chave_b64(b"\x00" * 16)
        )
        with pytest.raises(ValueError, match="32 bytes"):
            settings.master_key()

    def test_espacos_sao_ignorados(self) -> None:
        settings = Settings(environment="development", master_encryption_key=f"  {chave_b64()}  ")
        assert settings.master_key() == b"\x01" * 32


class TestAmbiente:
    def test_producao_e_reconhecida(self) -> None:
        assert Settings(environment="production").is_production is True
        assert Settings(environment="development").is_production is False

    def test_test_e_desenvolvimento(self) -> None:
        assert Settings(environment="test").is_development is True
        assert Settings(environment="staging").is_development is False

    def test_log_level_invalido_falha(self) -> None:
        with pytest.raises(ValueError, match="LOG_LEVEL"):
            Settings(log_level="barulhento")

    def test_log_level_normalizado(self) -> None:
        assert Settings(log_level=" debug ").log_level == "DEBUG"


class TestPadroes:
    def test_aliquotas_de_referencia_2026(self) -> None:
        settings = Settings()
        assert settings.rtc_cbs_aliquota_2026 == Decimal("0.009")
        assert settings.rtc_ibs_aliquota_2026 == Decimal("0.001")

    def test_limite_de_pagina_coerente(self) -> None:
        settings = Settings()
        assert settings.api_page_size_default <= settings.api_page_size_max
