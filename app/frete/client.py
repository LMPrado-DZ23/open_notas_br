"""Cliente de cotação de frete do Melhor Envio.

O modelo comercial definido pelo solicitante: **o frete é cotado e pago pelo
cliente final**. Isso separa duas responsabilidades no código:

- **cotação** devolve preço e prazo para o lojista exibir ao cliente final;
- **compra da etiqueta** usa o saldo da carteira do lojista. O dinheiro do frete
  veio do cliente, mas quem compra é o lojista — por isso a compra nunca é
  automática na cotação.

Consequência prática: cotar é operação **somente leitura**. Errar a cotação custa
uma resposta errada ao cliente; errar a compra custa dinheiro. Por isso estão em
métodos separados, e não em um `enviar()` que faz tudo.

[A VALIDAR] O contrato de `POST /api/v2/me/shipment/calculate` segue a documentação
lida em docs.melhorenvio.com.br, mas **não foi exercitado** contra a API ainda.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

from app.frete.constants import (
    CAMINHO_COTACAO,
    SERVICOS_IGNORADOS,
    USER_AGENT_PADRAO,
    base_url,
)

logger = logging.getLogger(__name__)


class ErroDeCotacao(Exception):
    """A cotação não pôde ser obtida ou veio inutilizável."""


@dataclass(frozen=True, slots=True)
class Produto:
    """Volume a cotar. Dimensões em centímetros, peso em quilogramas."""

    peso: Decimal
    altura: Decimal
    largura: Decimal
    comprimento: Decimal
    valor: Decimal
    quantidade: int = 1

    def para_api(self) -> dict[str, Any]:
        return {
            "id": "1",
            "width": float(self.largura),
            "height": float(self.altura),
            "length": float(self.comprimento),
            "weight": float(self.peso),
            "insurance_value": float(self.valor),
            "quantity": self.quantidade,
        }


@dataclass(frozen=True, slots=True)
class OpcaoFrete:
    """Uma transportadora/serviço cotado."""

    servico_id: int
    transportadora: str
    servico: str
    preco: Decimal
    prazo_dias: int
    moeda: str = "BRL"
    erro: str | None = None
    bruto: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def disponivel(self) -> bool:
        return self.erro is None and self.preco > 0


@dataclass(frozen=True, slots=True)
class Cotacao:
    opcoes: tuple[OpcaoFrete, ...]

    @property
    def disponiveis(self) -> tuple[OpcaoFrete, ...]:
        return tuple(o for o in self.opcoes if o.disponivel)

    @property
    def mais_barata(self) -> OpcaoFrete | None:
        disponiveis = self.disponiveis
        if not disponiveis:
            return None
        return min(disponiveis, key=lambda o: o.preco)

    @property
    def mais_rapida(self) -> OpcaoFrete | None:
        disponiveis = self.disponiveis
        if not disponiveis:
            return None
        return min(disponiveis, key=lambda o: o.prazo_dias)


def _decimal(valor: Any) -> Decimal:
    if valor in (None, ""):
        return Decimal("0")
    if isinstance(valor, str):
        # A API devolve preço com ponto decimal ("23.45"); string com vírgula
        # apareceria em resposta localizada e quebraria a conversão.
        return Decimal(valor.replace(",", "."))
    return Decimal(str(valor))


def _interpretar_opcao(bruto: dict[str, Any]) -> OpcaoFrete:
    erro = bruto.get("error")
    return OpcaoFrete(
        servico_id=int(bruto.get("id") or 0),
        transportadora=str(bruto.get("company", {}).get("name") or ""),
        servico=str(bruto.get("name") or ""),
        # `custom_price` é o preço que o LOJISTA definiu; `price` é o da
        # transportadora. Para exibir ao cliente final vale o do lojista — usar o
        # da transportadora mostraria um valor que ele não cobra.
        preco=_decimal(
            bruto.get("custom_price")
            if bruto.get("custom_price") not in (None, "", 0, "0")
            else bruto.get("price")
        ),
        prazo_dias=int(bruto.get("delivery_time") or bruto.get("custom_delivery_time") or 0),
        moeda=str(bruto.get("currency") or "BRL"),
        erro=str(erro) if erro else None,
        bruto=bruto,
    )


class MelhorEnvioClient:
    """Cliente sem estado de sessão: recebe o token a cada chamada.

    Sem cache de token aqui de propósito: quem guarda token é o serviço, que o
    persiste cifrado por tenant. Um cliente com cache interno esconderia token
    vencido até a operação falhar.
    """

    def __init__(
        self,
        access_token: str,
        *,
        sandbox: bool = True,
        timeout: float = 30.0,
        user_agent: str = USER_AGENT_PADRAO,
        transporte: httpx.BaseTransport | None = None,
    ) -> None:
        if not access_token:
            raise ErroDeCotacao("access_token ausente: o lojista precisa autorizar o app")
        self._token = access_token
        self._sandbox = sandbox
        self._timeout = timeout
        self._user_agent = user_agent
        self._transporte = transporte

    def _cabecalhos(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "User-Agent": self._user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def cotar(
        self,
        *,
        cep_origem: str,
        cep_destino: str,
        produtos: list[Produto],
    ) -> Cotacao:
        """Cota o frete. Somente leitura: não compra nada."""
        if not produtos:
            raise ErroDeCotacao("informe ao menos um produto para cotar")
        cep_origem = _so_digitos(cep_origem)
        cep_destino = _so_digitos(cep_destino)
        if len(cep_origem) != 8 or len(cep_destino) != 8:
            raise ErroDeCotacao("CEP deve ter 8 dígitos (origem e destino)")

        corpo = {
            "from": {"postal_code": cep_origem},
            "to": {"postal_code": cep_destino},
            "products": [p.para_api() for p in produtos],
            "options": {"receipt": False, "own_hand": False},
        }
        url = f"{base_url(self._sandbox).rstrip('/')}{CAMINHO_COTACAO}"

        try:
            with httpx.Client(
                timeout=self._timeout,
                headers=self._cabecalhos(),
                transport=self._transporte,
            ) as http:
                resposta = http.post(url, json=corpo)
        except httpx.HTTPError as exc:
            raise ErroDeCotacao(f"falha de rede na cotação: {exc}") from exc

        if resposta.status_code == 401:
            raise ErroDeCotacao(
                "token recusado (401): renove o acesso do Melhor Envio; "
                "o lojista pode precisar autorizar o aplicativo de novo"
            )
        if resposta.status_code >= 400:
            raise ErroDeCotacao(
                f"cotação recusada (HTTP {resposta.status_code}): {resposta.text[:300]}"
            )

        try:
            dados = resposta.json()
        except ValueError as exc:
            raise ErroDeCotacao("resposta da cotação não é JSON") from exc

        if not isinstance(dados, list):
            raise ErroDeCotacao(
                "resposta da cotação em formato inesperado (esperava lista de serviços): "
                + str(dados)[:200]
            )

        opcoes = [
            _interpretar_opcao(item)
            for item in dados
            if isinstance(item, dict) and str(item.get("id")) not in SERVICOS_IGNORADOS
        ]
        return Cotacao(opcoes=tuple(opcoes))

    def saldo(self) -> Decimal:
        """Saldo da carteira do lojista — é dele que sai o pagamento da etiqueta."""
        from app.frete.constants import CAMINHO_SALDO

        url = f"{base_url(self._sandbox).rstrip('/')}{CAMINHO_SALDO}"
        try:
            with httpx.Client(
                timeout=self._timeout,
                headers=self._cabecalhos(),
                transport=self._transporte,
            ) as http:
                resposta = http.get(url)
        except httpx.HTTPError as exc:
            raise ErroDeCotacao(f"falha de rede ao consultar saldo: {exc}") from exc
        if resposta.status_code >= 400:
            raise ErroDeCotacao(
                f"saldo indisponível (HTTP {resposta.status_code}): {resposta.text[:200]}"
            )
        return _decimal(resposta.json().get("balance"))


def _so_digitos(valor: str) -> str:
    return "".join(c for c in str(valor) if c.isdigit())
