"""Classificação de erro HTTP da SEFIN: HTML de gateway não é recusa fiscal.

Achado em execução real: a SEFIN respondeu `403` com HTML de IIS/WAF, e o cliente
classificou como `AUTENTICACAO` — o lojista concluiria "certificado recusado" e pararia de
tentar, quando o problema estava na infraestrutura na frente do serviço. Além disso o HTML
inteiro ia para a mensagem.
"""

from __future__ import annotations

from app.nfse.errors import TipoErroFiscal
from app.nfse.transport import ResultadoHTTP, erro_http

HTML_403 = (
    '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN">'
    "<html><head><title>403 - Forbidden</title></head>"
    "<body><h2>403 - Forbidden: Access is denied.</h2></body></html>"
)


def resultado(status: int, texto: str, json=None) -> ResultadoHTTP:
    return ResultadoHTTP(status, json, texto, 1.0)


class TestHtmlDeGateway:
    def test_403_html_e_indisponivel_nao_autenticacao(self) -> None:
        erro = erro_http(resultado(403, HTML_403), "a SEFIN recusou a DPS")
        assert erro.tipo is TipoErroFiscal.INDISPONIVEL

    def test_mensagem_explica_que_e_gateway(self) -> None:
        erro = erro_http(resultado(403, HTML_403), "a SEFIN recusou a DPS")
        assert "gateway" in erro.resumo or "WAF" in erro.resumo

    def test_html_nao_vira_mensagem_fiscal(self) -> None:
        erro = erro_http(resultado(403, HTML_403), "recusou")
        assert erro.mensagens == [], "HTML de gateway não é mensagem da SEFIN"

    def test_html_de_500_tambem_e_indisponivel(self) -> None:
        erro = erro_http(resultado(500, "<html><body>erro</body></html>"), "recusou")
        assert erro.tipo is TipoErroFiscal.INDISPONIVEL


class TestRespostaFiscal:
    def test_403_xml_continua_sendo_autenticacao(self) -> None:
        # Recusa fiscal de verdade: XML do leiaute com descrição.
        xml = "<retorno><mensagem><descricao>certificado invalido</descricao></mensagem></retorno>"
        erro = erro_http(resultado(403, xml), "recusou")
        assert erro.tipo is TipoErroFiscal.AUTENTICACAO

    def test_5xx_sem_html_e_indisponivel(self) -> None:
        assert (
            erro_http(resultado(503, "servico fora"), "recusou").tipo is TipoErroFiscal.INDISPONIVEL
        )

    def test_4xx_de_validacao_e_rejeicao(self) -> None:
        erro = erro_http(resultado(422, "<retorno><mensagem>x</mensagem></retorno>"), "recusou")
        assert erro.tipo is TipoErroFiscal.REJEICAO
