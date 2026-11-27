"""Escolha do adapter NFS-e não pode mandar emissão real para homologação (§44).

Defeito real encontrado por `mypy` e confirmado por leitura: três módulos montavam
`SefinNacionalClient(settings)`, passando `Settings` no parâmetro `ambiente`, que espera
`AmbienteFiscal`. Como `sefin_url()` compara com `is AmbienteFiscal.PRODUCAO`, qualquer objeto
que não seja o enum cai em **homologação** — sem exceção, sem log.

Além do ambiente errado, o cliente montado assim ia sem certificado de cliente: a emissão em lote
não conseguia mTLS. O caminho correto (serviço de emissão) monta o cliente com
`TenantFiscalConfig.ambiente` e o A1 do tenant.
"""

from __future__ import annotations

import inspect

import pytest
from app.core.config import Settings
from app.nfse.adapter import SefinMockAdapter
from app.nfse.constants import SEFIN_HOMOLOGACAO, SEFIN_PRODUCAO, sefin_url
from app.nfse.factory import montar_adapter


def _settings(**extra) -> Settings:
    base = {"environment": "test", "nfse_adapter": "sefin"}
    base.update(extra)
    return Settings(**base)


class TestFabrica:
    def test_mock_devolve_duble(self) -> None:
        assert isinstance(montar_adapter(_settings(nfse_adapter="mock")), SefinMockAdapter)

    def test_real_devolve_none_para_o_servico_montar(self) -> None:
        assert montar_adapter(_settings(nfse_adapter="sefin")) is None


class TestArmadilhaDoAmbiente:
    """Documenta por que passar `Settings` como `ambiente` é perigoso."""

    def test_objeto_que_nao_e_o_enum_cai_em_homologacao(self) -> None:
        assert sefin_url(_settings()) == SEFIN_HOMOLOGACAO  # type: ignore[arg-type]

    def test_enum_correto_escolhe_producao(self) -> None:
        from app.db.models.enums import AmbienteFiscal

        assert sefin_url(AmbienteFiscal.PRODUCAO) == SEFIN_PRODUCAO
        assert sefin_url(AmbienteFiscal.HOMOLOGACAO) == SEFIN_HOMOLOGACAO


class TestNinguemConstroiClienteRealForaDoServico:
    """Guarda estrutural: o cliente real só nasce em `app.nfse.servico.emitir`."""

    @pytest.mark.parametrize(
        "modulo",
        [
            "app.api.v1.lotes",
            "app.api.v1.integracoes",
            "app.worker.main",
        ],
    )
    def test_modulo_nao_instancia_sefin_nacional(self, modulo: str) -> None:
        fonte = inspect.getsource(__import__(modulo, fromlist=["*"]))
        assert "SefinNacionalClient(" not in fonte, (
            f"{modulo} voltou a montar o cliente real: use app.nfse.factory.montar_adapter "
            "e deixe o serviço de emissão passar ambiente do tenant + certificado"
        )
