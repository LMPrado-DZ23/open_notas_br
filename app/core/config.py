"""Configuração da aplicação, carregada de variáveis de ambiente.

Regra dura: **nenhum segredo tem valor padrão utilizável**. A chave-mestra do
cofre de certificados e o token administrativo vêm do ambiente. Em
desenvolvimento, a ausência da chave-mestra gera uma chave efêmera em memória com
aviso explícito no log; em produção a aplicação se recusa a subir.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

Ambiente = Literal["development", "staging", "production", "test"]

#: Chave efêmera de desenvolvimento, criada uma vez por processo.
_CHAVE_EFEMERA: bytes | None = None


class Settings(BaseSettings):
    """Configuração tipada da aplicação."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- aplicação ----------------------------------------------------
    environment: Ambiente = "development"
    log_level: str = "INFO"
    log_json: bool = True
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    api_page_size_default: int = 50
    api_page_size_max: int = 200
    #: Origens permitidas para CORS, separadas por vírgula. Vazio = nenhuma
    #: origem de navegador liberada (integração servidor-a-servidor não precisa).
    cors_origins: str = ""

    # -- banco --------------------------------------------------------
    database_url: str = "postgresql+asyncpg://notasbr:notasbr@127.0.0.1:55434/notasbr"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # -- redis --------------------------------------------------------
    redis_url: str = "redis://127.0.0.1:56379/0"

    # -- segredos -----------------------------------------------------
    master_encryption_key: str = ""
    admin_api_token: str = ""

    # -- NFS-e Nacional (Fase 3) --------------------------------------
    # [A VALIDAR] URL base não confirmada em fonte oficial. Vem do ambiente.
    sefin_base_url: str = ""
    sefin_homologacao_base_url: str = ""
    sefin_producao_base_url: str = ""
    sefin_timeout_seconds: int = 30
    #: Permite apontar a SEFIN para host que não seja `nfse.gov.br`.
    #: Só para espelho interno/homologação própria; desligado por padrão.
    sefin_permitir_host_nao_oficial: bool = False
    #: `sefin` = cliente real (padrão). `mock` = dublê determinístico, para
    #: demonstrar o fluxo sem certificado real e rodar a suíte em CI.
    nfse_adapter: str = "sefin"

    # -- CNPJ (Fase 3) ------------------------------------------------
    serpro_cnpj_token: str = ""
    serpro_cnpj_base_url: str = "https://gateway.apiserpro.serpro.gov.br/consulta-cnpj-df-v1"
    cnpj_cache_ttl_seconds: int = 86_400
    cnpj_rate_limit_per_second: int = 5
    cnpj_fallback_enabled: bool = True

    # -- Reforma Tributária (Fase 3) ----------------------------------
    # Alíquota é DADO versionado por competência, não constante de código.
    rtc_cbs_aliquota_2026: Decimal = Field(default=Decimal("0.009"))
    rtc_ibs_aliquota_2026: Decimal = Field(default=Decimal("0.001"))

    # -- webhooks (Fase 5) --------------------------------------------
    webhook_timeout_seconds: int = 10
    webhook_max_attempts: int = 5

    # -- derivados ----------------------------------------------------
    @field_validator("log_level")
    @classmethod
    def _normalizar_nivel(cls, valor: str) -> str:
        nivel = valor.upper().strip()
        if nivel not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"LOG_LEVEL inválido: {valor!r}")
        return nivel

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment in {"development", "test"}

    def master_key(self) -> bytes:
        """Resolve a chave-mestra AES-256 (32 bytes).

        - Definida no ambiente: precisa ser base64 de exatamente 32 bytes.
        - Ausente em produção: erro fatal. Nunca cai em chave padrão.
        - Ausente em desenvolvimento: gera chave efêmera e avisa.

        A chave efêmera é criada uma vez por processo. Certificado selado com ela
        fica ilegível depois de reiniciar — o que é aceitável em dev e inaceitável
        em produção, por isso a distinção.
        """
        global _CHAVE_EFEMERA

        bruto = self.master_encryption_key.strip()
        if bruto:
            try:
                chave = base64.b64decode(bruto, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError(
                    "MASTER_ENCRYPTION_KEY não é base64 válido. Gere com: "
                    'python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"'
                ) from exc
            if len(chave) != 32:
                raise ValueError(
                    f"MASTER_ENCRYPTION_KEY deve ter 32 bytes (AES-256); tem {len(chave)}"
                )
            return chave

        if self.is_production:
            raise ValueError(
                "MASTER_ENCRYPTION_KEY é obrigatória quando ENVIRONMENT=production. "
                "Sem ela, os certificados A1 não podem ser selados de forma recuperável."
            )

        if _CHAVE_EFEMERA is None:
            _CHAVE_EFEMERA = os.urandom(32)
            if self.environment != "test":
                logger.warning(
                    "MASTER_ENCRYPTION_KEY ausente: usando chave efêmera em memória. "
                    "Certificados selados agora ficarão ilegíveis após reiniciar. "
                    "Defina MASTER_ENCRYPTION_KEY antes de usar em qualquer ambiente real."
                )
        return _CHAVE_EFEMERA

    def reset_ephemeral_key(self) -> None:
        """Descarta a chave efêmera. Existe para isolamento entre testes."""
        global _CHAVE_EFEMERA
        _CHAVE_EFEMERA = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Configuração em cache (uma leitura de ambiente por processo)."""
    return Settings()


def reload_settings() -> Settings:
    """Descarta o cache e relê o ambiente. Usado por testes e por reload em dev."""
    get_settings.cache_clear()
    return get_settings()
