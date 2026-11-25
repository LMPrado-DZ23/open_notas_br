"""Testes do núcleo do Melhor Envio: OAuth e cotação.

Sem rede: o transporte HTTP é injetado. O que se verifica aqui é o contrato que
lemos na documentação — e, principalmente, o que o código faz quando a API
responde algo diferente do esperado.
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from app.frete.client import (
    Cotacao,
    ErroDeCotacao,
    MelhorEnvioClient,
    Produto,
    _interpretar_opcao,
)
from app.frete.constants import BASE_PRODUCAO, BASE_SANDBOX, ESCOPOS_COTACAO
from app.frete.oauth import (
    ErroDeAutorizacao,
    ErroMelhorEnvio,
    autorizacao_url,
    renovar,
    trocar_codigo,
)

PRODUTO = Produto(
    peso=Decimal("0.5"),
    altura=Decimal("10"),
    largura=Decimal("20"),
    comprimento=Decimal("30"),
    valor=Decimal("150.00"),
)


def resposta_json(status: int, corpo) -> httpx.Response:
    return httpx.Response(status, json=corpo, request=httpx.Request("POST", "https://x"))


class TestUrlDeAutorizacao:
    def test_monta_url_de_sandbox(self) -> None:
        url = autorizacao_url(
            client_id="123", redirect_uri="https://app/cb", state="tenant-a", sandbox=True
        )
        assert url.startswith(BASE_SANDBOX)
        assert "/oauth/authorize?" in url
        assert "client_id=123" in url
        assert "response_type=code" in url
        assert "state=tenant-a" in url

    def test_usa_producao_quando_pedido(self) -> None:
        url = autorizacao_url(
            client_id="1", redirect_uri="https://x", state="s", sandbox=False
        )
        assert url.startswith(BASE_PRODUCAO)

    def test_escopos_vao_separados_por_espaco(self) -> None:
        url = autorizacao_url(
            client_id="1", redirect_uri="https://x", state="s", escopos=("a", "b")
        )
        assert "scope=a+b" in url or "scope=a%20b" in url

    def test_escopo_padrao_e_so_cotacao(self) -> None:
        url = autorizacao_url(client_id="1", redirect_uri="https://x", state="s")
        assert ESCOPOS_COTACAO[0] in url
        assert "shipping-checkout" not in url, "não pedir compra sem precisar"

    def test_state_obrigatorio(self) -> None:
        # Sem state não há como amarrar o retorno ao tenant certo.
        with pytest.raises(ErroDeAutorizacao, match="state"):
            autorizacao_url(client_id="1", redirect_uri="https://x", state="")

    def test_client_id_obrigatorio(self) -> None:
        with pytest.raises(ErroDeAutorizacao):
            autorizacao_url(client_id="", redirect_uri="https://x", state="s")


class TestTrocaDeCodigo:
    def test_troca_com_sucesso(self, monkeypatch) -> None:
        capturado = {}

        def falso_post(self, url, json=None, headers=None):
            capturado["url"] = url
            capturado["corpo"] = json
            capturado["headers"] = headers
            return resposta_json(
                200,
                {
                    "access_token": "tok",
                    "refresh_token": "ref",
                    "expires_in": 2592000,
                    "token_type": "Bearer",
                },
            )

        monkeypatch.setattr(httpx.Client, "post", falso_post)
        token = trocar_codigo(
            code="abc", client_id="cid", client_secret="sec", redirect_uri="https://cb"
        )
        assert token.access_token == "tok"
        assert token.refresh_token == "ref"
        assert token.expira_em is not None
        assert capturado["corpo"]["grant_type"] == "authorization_code"
        assert capturado["corpo"]["code"] == "abc"
        assert capturado["url"].endswith("/oauth/token")
        assert "User-Agent" in capturado["headers"], "User-Agent é obrigatório pela API"

    def test_client_invalid_da_mensagem_util(self, monkeypatch) -> None:
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, json=None, headers=None: resposta_json(
                401, {"error": "Client invalid"}
            ),
        )
        with pytest.raises(ErroDeAutorizacao, match="redirect_uri"):
            trocar_codigo(code="c", client_id="i", client_secret="s", redirect_uri="https://x")

    def test_codigo_vazio(self) -> None:
        with pytest.raises(ErroDeAutorizacao, match="código"):
            trocar_codigo(code="", client_id="i", client_secret="s", redirect_uri="https://x")

    def test_resposta_sem_access_token(self, monkeypatch) -> None:
        monkeypatch.setattr(
            httpx.Client,
            "post",
            lambda self, url, json=None, headers=None: resposta_json(200, {"foo": "bar"}),
        )
        with pytest.raises(ErroMelhorEnvio, match="access_token"):
            trocar_codigo(code="c", client_id="i", client_secret="s", redirect_uri="https://x")


class TestRenovacao:
    def test_renova(self, monkeypatch) -> None:
        capturado = {}

        def falso_post(self, url, json=None, headers=None):
            capturado["corpo"] = json
            return resposta_json(200, {"access_token": "novo", "refresh_token": "ref2"})

        monkeypatch.setattr(httpx.Client, "post", falso_post)
        token = renovar(refresh_token="ref", client_id="i", client_secret="s")
        assert token.access_token == "novo"
        assert token.refresh_token == "ref2"
        assert capturado["corpo"]["grant_type"] == "refresh_token"

    def test_sem_refresh_token(self) -> None:
        with pytest.raises(ErroDeAutorizacao, match="refresh_token"):
            renovar(refresh_token="", client_id="i", client_secret="s")


class TestValidade:
    def test_token_sem_expiracao_nunca_esta_expirado(self) -> None:
        from app.frete.oauth import TokenOAuth

        assert TokenOAuth(access_token="t", refresh_token=None, expira_em=None).expirado is False

    def test_token_vencendo_em_2_min_conta_como_expirado(self) -> None:
        from datetime import UTC, datetime, timedelta

        from app.frete.oauth import TokenOAuth

        token = TokenOAuth(
            access_token="t",
            refresh_token="r",
            expira_em=datetime.now(UTC) + timedelta(minutes=2),
        )
        assert token.expirado is True, "margem de 5 min evita vencer no meio da compra"

    def test_cabecalho_bearer(self) -> None:
        from app.frete.oauth import TokenOAuth

        cabecalho = TokenOAuth(access_token="abc", refresh_token=None, expira_em=None).cabecalho()
        assert cabecalho == {"Authorization": "Bearer abc"}


def cliente_com(resposta) -> MelhorEnvioClient:
    def manipulador(request: httpx.Request) -> httpx.Response:
        return resposta

    return MelhorEnvioClient(
        "token", sandbox=True, transporte=httpx.MockTransport(manipulador)
    )


class TestCotacao:
    def test_cotacao_com_duas_opcoes(self) -> None:
        corpo = [
            {
                "id": 3,
                "name": "PAC",
                "price": "23.45",
                "delivery_time": 8,
                "company": {"name": "Correios"},
                "currency": "BRL",
            },
            {
                "id": 4,
                "name": "SEDEX",
                "price": "41.90",
                "delivery_time": 2,
                "company": {"name": "Correios"},
                "currency": "BRL",
            },
        ]
        cliente = cliente_com(httpx.Response(200, json=corpo))
        cotacao = cliente.cotar(cep_origem="01001000", cep_destino="20040020", produtos=[PRODUTO])
        assert isinstance(cotacao, Cotacao)
        assert len(cotacao.opcoes) == 2
        assert cotacao.mais_barata.servico == "PAC"
        assert cotacao.mais_barata.preco == Decimal("23.45")
        assert cotacao.mais_rapida.servico == "SEDEX"
        assert cotacao.mais_rapida.prazo_dias == 2

    def test_servico_sem_preco_nao_entra_como_disponivel(self) -> None:
        corpo = [{"id": 3, "name": "PAC", "price": None, "error": "CEP inválido"}]
        cotacao = cliente_com(httpx.Response(200, json=corpo)).cotar(
            cep_origem="01001000", cep_destino="20040020", produtos=[PRODUTO]
        )
        assert cotacao.disponiveis == ()
        assert cotacao.mais_barata is None
        assert cotacao.opcoes[0].erro == "CEP inválido"

    def test_401_pede_renovacao(self) -> None:
        cliente = cliente_com(httpx.Response(401, json={"message": "Unauthenticated"}))
        with pytest.raises(ErroDeCotacao, match="renove"):
            cliente.cotar(cep_origem="01001000", cep_destino="20040020", produtos=[PRODUTO])

    def test_cep_invalido_falha_antes_da_rede(self) -> None:
        cliente = cliente_com(httpx.Response(200, json=[]))
        with pytest.raises(ErroDeCotacao, match="8 dígitos"):
            cliente.cotar(cep_origem="123", cep_destino="20040020", produtos=[PRODUTO])

    def test_sem_produto(self) -> None:
        cliente = cliente_com(httpx.Response(200, json=[]))
        with pytest.raises(ErroDeCotacao, match="ao menos um produto"):
            cliente.cotar(cep_origem="01001000", cep_destino="20040020", produtos=[])

    def test_resposta_que_nao_e_lista(self) -> None:
        cliente = cliente_com(httpx.Response(200, json={"erro": "x"}))
        with pytest.raises(ErroDeCotacao, match="formato inesperado"):
            cliente.cotar(cep_origem="01001000", cep_destino="20040020", produtos=[PRODUTO])

    def test_sem_token(self) -> None:
        with pytest.raises(ErroDeCotacao, match="access_token"):
            MelhorEnvioClient("")


class TestInterpretacao:
    def test_preco_com_virgula_nao_quebra(self) -> None:
        # Resposta localizada pode vir com vírgula; converter errado daria preço 100x.
        opcao = _interpretar_opcao({"id": 3, "price": "23,45", "delivery_time": 8})
        assert opcao.preco == Decimal("23.45")

    def test_custom_price_prefere_o_preco_do_lojista(self) -> None:
        # `price` é o da transportadora; `custom_price` é o que o lojista cobra.
        # Mostrar o da transportadora exibiria ao cliente um valor que não é cobrado.
        opcao = _interpretar_opcao(
            {"id": 3, "price": "20.00", "custom_price": "18.50", "delivery_time": 5}
        )
        assert opcao.preco == Decimal("18.50")

    def test_sem_custom_price_usa_o_da_transportadora(self) -> None:
        opcao = _interpretar_opcao({"id": 3, "price": "20.00", "delivery_time": 5})
        assert opcao.preco == Decimal("20.00")

    def test_custom_price_zero_cai_no_price(self) -> None:
        opcao = _interpretar_opcao(
            {"id": 3, "price": "20.00", "custom_price": "0", "delivery_time": 5}
        )
        assert opcao.preco == Decimal("20.00"), "zero não é preço válido de frete"
