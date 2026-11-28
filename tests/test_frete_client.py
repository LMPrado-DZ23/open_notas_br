"""Cliente de cotação do Melhor Envio: cada resposta vira erro com instrução própria.

401 não é "erro qualquer": é token recusado e o lojista pode precisar reautorizar. 4xx/5xx, resposta
que não é JSON, formato inesperado e falha de rede têm mensagens distintas porque a ação do integrador
muda em cada caso. Tudo com transporte falso — nenhuma chamada de rede.
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from app.frete.client import (
    Cotacao,
    ErroDeCotacao,
    MelhorEnvioClient,
    OpcaoFrete,
    Produto,
    _decimal,
    _interpretar_opcao,
)


class RespostaFalsa:
    def __init__(self, status: int, json: object = None, texto: str = "") -> None:
        self.status_code = status
        self._json = json
        self.text = texto

    def json(self):
        if isinstance(self._json, Exception):
            raise self._json
        return self._json


class TransporteFalso(httpx.BaseTransport):
    """Transporte que devolve o que o teste mandar, sem abrir socket."""

    def __init__(self, resposta: RespostaFalsa | Exception) -> None:
        self._resposta = resposta
        self.chamadas: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.chamadas.append(request)
        if isinstance(self._resposta, Exception):
            raise self._resposta
        if isinstance(self._resposta._json, Exception):
            corpo = b"<html>erro</html>"  # corpo não-JSON: `json()` levanta
        elif self._resposta._json is not None:
            import json as _json

            corpo = _json.dumps(self._resposta._json).encode()
        else:
            corpo = self._resposta.text.encode()
        return httpx.Response(
            status_code=self._resposta.status_code,
            content=corpo,
            request=request,
        )


def _provedor(transporte: TransporteFalso) -> MelhorEnvioClient:
    return MelhorEnvioClient("token", sandbox=True, transporte=transporte, timeout=1.0)


class TestPrecos:
    def test_decimal_de_none_e_vazio(self) -> None:
        assert _decimal(None) == Decimal("0")
        assert _decimal("") == Decimal("0")

    def test_decimal_aceita_virgula(self) -> None:
        assert _decimal("23,45") == Decimal("23.45")

    def test_decimal_aceita_numero(self) -> None:
        assert _decimal(23.45) == Decimal("23.45")

    def test_interpretar_opcao_usa_campos_da_api(self) -> None:
        opcao = _interpretar_opcao(
            {
                "id": 1,
                "name": "PAC",
                "price": "23.45",
                "delivery_time": 5,
                "company": {"name": "Correios"},
            }
        )

        assert opcao.servico_id == 1
        assert opcao.preco == Decimal("23.45")


class TestCotacao:
    def test_mais_barata_e_mais_rapida(self) -> None:
        barata = OpcaoFrete(
            servico_id=1, transportadora="A", servico="Eco", preco=Decimal("10"), prazo_dias=9
        )
        rapida = OpcaoFrete(
            servico_id=2, transportadora="B", servico="Exp", preco=Decimal("30"), prazo_dias=1
        )
        cotacao = Cotacao(opcoes=(barata, rapida))

        assert cotacao.mais_barata is barata
        assert cotacao.mais_rapida is rapida

    def test_cotacao_vazia_nao_tem_extremos(self) -> None:
        cotacao = Cotacao(opcoes=())

        assert cotacao.mais_barata is None and cotacao.mais_rapida is None


class TestRecusas:
    def test_falha_de_rede_vira_erro_de_cotacao(self) -> None:
        provedor = _provedor(TransporteFalso(httpx.ConnectError("sem rota")))

        with pytest.raises(ErroDeCotacao) as erro:
            provedor.cotar(
                cep_origem="72900000",
                cep_destino="01001000",
                produtos=[
                    Produto(peso=1.0, altura=1, largura=1, comprimento=1, valor=10.0, quantidade=1)
                ],
            )

        assert "falha de rede" in str(erro.value)

    def test_401_pede_reautorizacao(self) -> None:
        provedor = _provedor(TransporteFalso(RespostaFalsa(401)))

        with pytest.raises(ErroDeCotacao) as erro:
            provedor.cotar(
                cep_origem="72900000",
                cep_destino="01001000",
                produtos=[
                    Produto(peso=1.0, altura=1, largura=1, comprimento=1, valor=10.0, quantidade=1)
                ],
            )

        assert "401" in str(erro.value) and "autorizar" in str(erro.value)

    def test_erro_http_mostra_corpo(self) -> None:
        provedor = _provedor(TransporteFalso(RespostaFalsa(422, texto="cep inválido")))

        with pytest.raises(ErroDeCotacao) as erro:
            provedor.cotar(
                cep_origem="72900000",
                cep_destino="01001000",
                produtos=[
                    Produto(peso=1.0, altura=1, largura=1, comprimento=1, valor=10.0, quantidade=1)
                ],
            )

        assert "cep inválido" in str(erro.value)

    def test_resposta_que_nao_e_json(self) -> None:
        provedor = _provedor(TransporteFalso(RespostaFalsa(200, json=ValueError("html"))))

        with pytest.raises(ErroDeCotacao) as erro:
            provedor.cotar(
                cep_origem="72900000",
                cep_destino="01001000",
                produtos=[
                    Produto(peso=1.0, altura=1, largura=1, comprimento=1, valor=10.0, quantidade=1)
                ],
            )

        assert "não é JSON" in str(erro.value)

    def test_formato_inesperado_mostra_o_que_veio(self) -> None:
        provedor = _provedor(TransporteFalso(RespostaFalsa(200, json={"erro": "x"})))

        with pytest.raises(ErroDeCotacao) as erro:
            provedor.cotar(
                cep_origem="72900000",
                cep_destino="01001000",
                produtos=[
                    Produto(peso=1.0, altura=1, largura=1, comprimento=1, valor=10.0, quantidade=1)
                ],
            )

        assert "formato inesperado" in str(erro.value)


class TestSaldo:
    def test_erro_de_rede_no_saldo(self) -> None:
        provedor = _provedor(TransporteFalso(httpx.ConnectError("sem rota")))

        with pytest.raises(ErroDeCotacao) as erro:
            provedor.saldo()

        assert "saldo" in str(erro.value)

    def test_http_erro_no_saldo(self) -> None:
        provedor = _provedor(TransporteFalso(RespostaFalsa(500, texto="caiu")))

        with pytest.raises(ErroDeCotacao) as erro:
            provedor.saldo()

        assert "indisponível" in str(erro.value)

    def test_sem_produto_recusa(self) -> None:
        provedor = _provedor(TransporteFalso(RespostaFalsa(200, json=[])))

        with pytest.raises(ErroDeCotacao) as erro:
            provedor.cotar(cep_origem="72900000", cep_destino="01001000", produtos=[])

        assert "ao menos um produto" in str(erro.value)


class TestSucesso:
    def test_cotacao_com_um_servico(self) -> None:
        corpo = [
            {
                "id": 3,
                "name": "PAC",
                "price": "23.45",
                "delivery_time": 5,
                "company": {"name": "Correios"},
            }
        ]
        provedor = _provedor(TransporteFalso(RespostaFalsa(200, json=corpo)))

        cotacao = provedor.cotar(
            cep_origem="72900000",
            cep_destino="01001000",
            produtos=[
                Produto(peso=1.0, altura=1, largura=1, comprimento=1, valor=10.0, quantidade=1)
            ],
        )

        assert len(cotacao.opcoes) == 1
        assert cotacao.mais_barata is not None
        assert cotacao.mais_barata.preco == Decimal("23.45")

    def test_saldo_devolve_decimal(self) -> None:
        provedor = _provedor(TransporteFalso(RespostaFalsa(200, json={"balance": "150.75"})))

        assert provedor.saldo() == Decimal("150.75")

    def test_token_ausente_recusa_construir(self) -> None:
        with pytest.raises(ErroDeCotacao) as erro:
            MelhorEnvioClient("")

        assert "access_token" in str(erro.value)

    def test_cep_curto_recusa_antes_de_chamar(self) -> None:
        transporte = TransporteFalso(RespostaFalsa(200, json=[]))
        provedor = _provedor(transporte)
        produto = Produto(peso=1.0, altura=1, largura=1, comprimento=1, valor=10.0, quantidade=1)

        with pytest.raises(ErroDeCotacao) as erro:
            provedor.cotar(cep_origem="7290000", cep_destino="01001000", produtos=[produto])

        assert "8 dígitos" in str(erro.value)
        assert transporte.chamadas == [], "CEP inválido não pode gastar chamada"
