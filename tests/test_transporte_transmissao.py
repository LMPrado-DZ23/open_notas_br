"""Transmissão de CT-e/MDF-e: parâmetros do WSDL travados e recusa de documento não assinado."""

from __future__ import annotations

import pytest
from app.cte import transmissao as cte_tx
from app.mdfe import transmissao as mdfe_tx


class TestParametrosCTe:
    def test_soap_e_12(self) -> None:
        assert cte_tx.SOAP_VERSAO == "1.2"

    def test_wrapper_e_cte_dados_msg(self) -> None:
        assert cte_tx.ELEMENTO_DADOS == "cteDadosMsg"

    def test_acao_e_da_recepcao_sincrona(self) -> None:
        assert f"{cte_tx.NS_SERVICO}/cteRecepcao" == cte_tx.ACAO

    def test_namespace_e_o_da_v4(self) -> None:
        assert cte_tx.NS_SERVICO.endswith("CTeRecepcaoSincV4")


class TestParametrosMDFe:
    def test_soap_e_12(self) -> None:
        assert mdfe_tx.SOAP_VERSAO == "1.2"

    def test_wrapper_e_mdfe_dados_msg(self) -> None:
        assert mdfe_tx.ELEMENTO_DADOS == "mdfeDadosMsg"

    def test_acao_e_da_recepcao(self) -> None:
        assert f"{mdfe_tx.NS_SERVICO}/mdfeRecepcao" == mdfe_tx.ACAO


class TestRecusaSemAssinatura:
    async def test_cte_sem_assinatura_nao_vai_para_a_rede(self) -> None:
        with pytest.raises(ValueError, match="assinado"):
            await cte_tx.enviar(None, url="https://x", cte_assinado=b"<CTe/>")  # type: ignore[arg-type]

    async def test_mdfe_sem_assinatura_nao_vai_para_a_rede(self) -> None:
        with pytest.raises(ValueError, match="assinado"):
            await mdfe_tx.enviar(None, url="https://x", mdfe_assinado=b"<MDFe/>")  # type: ignore[arg-type]
