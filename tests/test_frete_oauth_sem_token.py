"""Nenhum token pode aparecer no texto de erro do OAuth do frete.

O provedor pode devolver `refresh_token` sem `access_token` (resposta parcial). Se a mensagem despejar o
corpo, o refresh token vai para o log e para o corpo do erro HTTP — credencial persistente exposta em
dois lugares que sobrevivem à requisição.

Transporte dublado: nenhuma chamada de rede.
"""

from __future__ import annotations

import httpx
import pytest
from app.frete import oauth
from app.frete.oauth import ErroMelhorEnvio

SEGREDO = "refresh-SUPER-secreto-123"


class RespostaFalsa(httpx.Response):
    """Resposta do httpx com corpo controlado, sem abrir socket."""

    def __init__(self, corpo: dict, status: int = 200) -> None:
        super().__init__(status_code=status, json=corpo, request=httpx.Request("POST", "http://t"))


class ClienteFalso:
    def __init__(self, corpo: dict, status: int = 200) -> None:
        self._corpo = corpo
        self._status = status

    def __enter__(self) -> ClienteFalso:
        return self

    def __exit__(self, *a) -> None:
        return None

    def post(self, *a, **k) -> RespostaFalsa:
        return RespostaFalsa(self._corpo, self._status)


def _dublar(monkeypatch, corpo: dict, status: int = 200) -> None:
    monkeypatch.setattr(oauth.httpx, "Client", lambda **k: ClienteFalso(corpo, status))


def _trocar() -> None:
    oauth.trocar_codigo(
        code="codigo", client_id="id", client_secret="secret", redirect_uri="https://app/cb"
    )


class TestSemAccessToken:
    def test_mensagem_nao_contem_o_refresh_token(self, monkeypatch) -> None:
        _dublar(monkeypatch, {"refresh_token": SEGREDO, "scope": "shipping"})

        with pytest.raises(ErroMelhorEnvio) as erro:
            _trocar()

        mensagem = str(erro.value)
        assert SEGREDO not in mensagem, "refresh token vazou na mensagem de erro"
        assert "refresh_token" in mensagem, "os NOMES das chaves devem aparecer, para diagnóstico"

    def test_resposta_vazia_diz_que_nao_veio_chave(self, monkeypatch) -> None:
        _dublar(monkeypatch, {})

        with pytest.raises(ErroMelhorEnvio) as erro:
            _trocar()

        assert "nenhuma" in str(erro.value)

    def test_resposta_com_access_token_continua_funcionando(self, monkeypatch) -> None:
        _dublar(monkeypatch, {"access_token": "a", "refresh_token": "r", "scope": "s"})

        token = oauth.trocar_codigo(
            code="codigo", client_id="id", client_secret="secret", redirect_uri="https://app/cb"
        )

        assert token.access_token == "a"
        assert token.refresh_token == "r"
