"""OAuth2 do Melhor Envio: autorização, troca de código e renovação.

O fluxo é o padrão *authorization code*: o lojista autoriza o aplicativo no
navegador, o Melhor Envio devolve um `code` na `redirect_uri`, e esse código é
trocado por `access_token` + `refresh_token`.

Duas consequências de projeto:

- **O token é por tenant.** Cada lojista autoriza o mesmo aplicativo e recebe o
  próprio token. Guardar um token global misturaria etiquetas de lojas diferentes.
- **O token precisa de renovação silenciosa.** Ele vale 30 dias; uma etiqueta que
  falha porque o token venceu é um erro operacional evitável. Quem chama deve
  renovar antes de cada operação e persistir o par novo (o `refresh_token` também
  muda a cada renovação).

O `User-Agent` é obrigatório pela documentação e carrega nome do app e contato.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.frete.constants import (
    CAMINHO_AUTORIZACAO,
    CAMINHO_TOKEN,
    ESCOPOS_COTACAO,
    USER_AGENT_PADRAO,
    base_url,
)

logger = logging.getLogger(__name__)


class ErroMelhorEnvio(Exception):
    """Falha na comunicação ou na resposta do Melhor Envio."""


class ErroDeAutorizacao(ErroMelhorEnvio):
    """O código de autorização não pôde ser trocado por token."""


@dataclass(frozen=True, slots=True)
class TokenOAuth:
    """Par de tokens devolvido pela API."""

    access_token: str
    refresh_token: str | None
    expira_em: datetime | None
    escopo: str | None = None
    tipo: str = "Bearer"

    @property
    def expirado(self) -> bool:
        if self.expira_em is None:
            return False
        # Margem de 5 minutos: renovar em cima do vencimento arrisca correr no
        # meio de uma operação de compra, que não deve falhar por isso.
        return datetime.now(UTC) >= self.expira_em - timedelta(minutes=5)

    def cabecalho(self) -> dict[str, str]:
        return {"Authorization": f"{self.tipo} {self.access_token}"}


def autorizacao_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    sandbox: bool = True,
    escopos: tuple[str, ...] = ESCOPOS_COTACAO,
) -> str:
    """URL para o lojista autorizar o aplicativo no navegador.

    `state` volta junto do `code`; amarrar o `state` ao tenant é o que impede
    trocar o código de uma loja pela sessão de outra.
    """
    if not client_id or not redirect_uri:
        raise ErroDeAutorizacao("client_id e redirect_uri são obrigatórios")
    if not state:
        raise ErroDeAutorizacao(
            "state é obrigatório: sem ele não há como amarrar o retorno a um tenant"
        )
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "scope": " ".join(escopos),
    }
    return f"{base_url(sandbox).rstrip('/')}{CAMINHO_AUTORIZACAO}?{urlencode(params)}"


def _corpo_token(dados: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in dados.items() if v}


def _requisitar_token(
    *,
    client_id: str,
    client_secret: str,
    dados: dict[str, str],
    sandbox: bool,
    user_agent: str = USER_AGENT_PADRAO,
    timeout: float = 30.0,
) -> TokenOAuth:
    url = f"{base_url(sandbox).rstrip('/')}{CAMINHO_TOKEN}"
    cabecalhos = {
        "User-Agent": user_agent,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    corpo = _corpo_token({"client_id": client_id, "client_secret": client_secret, **dados})

    try:
        with httpx.Client(timeout=timeout) as http:
            resposta = http.post(url, json=corpo, headers=cabecalhos)
    except httpx.HTTPError as exc:
        raise ErroMelhorEnvio(f"falha de rede ao falar com o Melhor Envio: {exc}") from exc

    if resposta.status_code >= 400:
        # A API responde `Client invalid` quando a redirect_uri do corpo difere da
        # cadastrada no app. Mensagem própria porque é o erro mais comum.
        texto = resposta.text[:400]
        if "Client invalid" in texto:
            raise ErroDeAutorizacao(
                "a API recusou a autorização (Client invalid): a redirect_uri "
                "enviada precisa ser idêntica à cadastrada no aplicativo"
            )
        raise ErroMelhorEnvio(
            f"Melhor Envio recusou o token (HTTP {resposta.status_code}): {texto}"
        )

    try:
        dados_resposta = resposta.json()
    except ValueError as exc:
        raise ErroMelhorEnvio("resposta do token não é JSON") from exc

    access = dados_resposta.get("access_token")
    if not access:
        # Só os NOMES das chaves: despejar o corpo pode colocar `refresh_token` no texto
        # da exceção, que vai para log e para o corpo do erro.
        chaves = ", ".join(sorted(str(k) for k in dados_resposta)) or "nenhuma"
        raise ErroMelhorEnvio(f"resposta sem access_token (chaves recebidas: {chaves})")

    expira_em = None
    if expira_em_segundos := dados_resposta.get("expires_in"):
        try:
            expira_em = datetime.now(UTC) + timedelta(seconds=int(expira_em_segundos))
        except (TypeError, ValueError):
            expira_em = None

    return TokenOAuth(
        access_token=access,
        refresh_token=dados_resposta.get("refresh_token"),
        expira_em=expira_em,
        escopo=dados_resposta.get("scope"),
        tipo=dados_resposta.get("token_type") or "Bearer",
    )


def trocar_codigo(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    sandbox: bool = True,
    user_agent: str = USER_AGENT_PADRAO,
) -> TokenOAuth:
    """Troca o `code` devolvido na `redirect_uri` pelo primeiro par de tokens."""
    if not code:
        raise ErroDeAutorizacao("código de autorização ausente")
    return _requisitar_token(
        client_id=client_id,
        client_secret=client_secret,
        dados={
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        },
        sandbox=sandbox,
        user_agent=user_agent,
    )


def renovar(
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    sandbox: bool = True,
    user_agent: str = USER_AGENT_PADRAO,
) -> TokenOAuth:
    """Renova o acesso. O `refresh_token` devolvido **substitui** o anterior."""
    if not refresh_token:
        raise ErroDeAutorizacao(
            "refresh_token ausente: sem ele o lojista precisa autorizar de novo"
        )
    return _requisitar_token(
        client_id=client_id,
        client_secret=client_secret,
        dados={"grant_type": "refresh_token", "refresh_token": refresh_token},
        sandbox=sandbox,
        user_agent=user_agent,
    )
