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


class _ClienteFalso:
    """Captura o que seria enviado, sem tocar a rede."""

    def __init__(self) -> None:
        self.chamada: dict[str, object] = {}

    async def chamar(self, **kwargs: object):
        self.chamada = kwargs
        return "resposta-falsa"


class TestCaminhoDeChamada:
    """Exercita `enviar()` inteiro com cliente falso: sem rede, mas com o caminho real."""

    async def test_cte_usa_os_parametros_do_wsdl(self) -> None:
        cliente = _ClienteFalso()
        xml = b'<CTe><Signature xmlns="http://www.w3.org/2000/09/xmldsig#"/></CTe>'
        resposta = await cte_tx.enviar(cliente, url="https://exemplo/cte", cte_assinado=xml)  # type: ignore[arg-type]
        assert resposta == "resposta-falsa"
        assert cliente.chamada["url"] == "https://exemplo/cte"
        assert cliente.chamada["xml_fiscal"] == xml
        assert cliente.chamada["ns_servico"] == cte_tx.NS_SERVICO
        assert cliente.chamada["soap_versao"] == "1.2"
        assert cliente.chamada["elemento_dados"] == "cteDadosMsg"

    async def test_mdfe_usa_os_parametros_do_wsdl(self) -> None:
        cliente = _ClienteFalso()
        xml = b'<MDFe><Signature xmlns="http://www.w3.org/2000/09/xmldsig#"/></MDFe>'
        await mdfe_tx.enviar(cliente, url="https://exemplo/mdfe", mdfe_assinado=xml)  # type: ignore[arg-type]
        assert cliente.chamada["ns_servico"] == mdfe_tx.NS_SERVICO
        assert cliente.chamada["soap_versao"] == "1.2"
        assert cliente.chamada["elemento_dados"] == "mdfeDadosMsg"
