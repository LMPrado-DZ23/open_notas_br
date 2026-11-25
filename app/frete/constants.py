"""Constantes da API do Melhor Envio.

Fonte: documentação oficial em docs.melhorenvio.com.br, lida em 25/11/2026.

[CONFIRMADO] na documentação:
- autorização por OAuth2, com ``client_id``, ``redirect_uri``, ``response_type=code``
  e ``scope`` separado por espaço;
- a ``redirect_uri`` precisa ser **idêntica** à cadastrada no app, senão a API
  devolve ``Client invalid``;
- token em ``POST {base}/oauth/token`` com ``grant_type=authorization_code`` ou
  ``refresh_token``;
- o cabeçalho ``User-Agent`` é **obrigatório** e deve trazer nome do app e e-mail
  de contato;
- ``access_token`` vale 2.592.000 s (30 dias) e vem com ``refresh_token``.

[A VALIDAR] Os caminhos de cotação, carrinho e etiqueta não foram exercitados
contra a API ainda — estão no cliente, mas só a chamada real confirma.
"""

from __future__ import annotations

BASE_PRODUCAO = "https://www.melhorenvio.com.br"
BASE_SANDBOX = "https://sandbox.melhorenvio.com.br"

CAMINHO_AUTORIZACAO = "/oauth/authorize"
CAMINHO_TOKEN = "/oauth/token"

#: Cotação de frete por produtos.
CAMINHO_COTACAO = "/api/v2/me/shipment/calculate"
#: Inserir no carrinho, comprar, gerar e imprimir (fluxo de etiqueta).
CAMINHO_CARRINHO = "/api/v2/me/cart"
CAMINHO_CHECKOUT = "/api/v2/me/shipment/checkout"
CAMINHO_GERAR = "/api/v2/me/shipment/generate"
CAMINHO_IMPRIMIR = "/api/v2/me/shipment/print"
CAMINHO_RASTREIO = "/api/v2/me/shipment/tracking"
CAMINHO_SALDO = "/api/v2/me/balance"

#: Escopos mínimos para o fluxo "cotar → comprar → gerar → imprimir".
#: Pedir só o necessário: escopo a mais é acesso a mais que o sistema não usa.
ESCOPOS_COTACAO = ("shipping-calculate",)

ESCOPOS_ETIQUETA = (
    "shipping-calculate",
    "shipping-checkout",
    "shipping-generate",
    "shipping-print",
    "shipping-cancel",
    "shipping-tracking",
    "orders-read",
    "cart-read",
    "cart-write",
    "users-read",
)

#: Serviços que não são transportadora e aparecem na cotação sem preço útil.
SERVICOS_IGNORADOS = ("1", "2")

#: A API exige User-Agent com nome do app e e-mail de contato.
USER_AGENT_PADRAO = "open_notas_br (integracao fiscal; contato@dz23.com.br)"


def base_url(sandbox: bool) -> str:
    return BASE_SANDBOX if sandbox else BASE_PRODUCAO
