"""A demo E2E recusa rodar contra adaptador NFS-e real (§43).

`scripts/demo_e2e.py` emite NFS-e de ponta a ponta. Numa instância com `NFSE_ADAPTER=sefin` isso
seria emissão fiscal de verdade — fora da autorização de quem só quer exercitar o fluxo. O
dublê é indistinguível na resposta de propósito, então a decisão tem de vir do `/health`.
"""

from __future__ import annotations

import pytest
from scripts import demo_e2e


class _Resposta:
    def __init__(self, payload: dict) -> None:
        self.status_code = 200
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _Escrita(Exception):
    """Sentinela: chegar em `post` significa que a guarda deixou passar."""


class _ClienteFalso:
    def __init__(self, adaptador: str) -> None:
        self._adaptador = adaptador
        self.escritas: list[str] = []

    def __enter__(self) -> _ClienteFalso:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def get(self, url: str):
        return _Resposta({"status": "ok", "versao": "0", "nfse_adapter": self._adaptador})

    def post(self, url: str, **kwargs):
        self.escritas.append(url)
        raise _Escrita(url)


@pytest.fixture(autouse=True)
def _silencia(capsys):
    yield
    capsys.readouterr()


def test_recusa_antes_de_escrever_com_adapter_real(monkeypatch) -> None:
    cliente = _ClienteFalso("sefin")
    monkeypatch.setattr(demo_e2e.httpx, "Client", lambda **kwargs: cliente)

    assert demo_e2e.main() == 2
    assert cliente.escritas == [], "a demo nao pode criar tenant antes de saber o adaptador"


def test_segue_quando_o_adapter_e_mock(monkeypatch) -> None:
    """A guarda não pode bloquear o caminho legítimo."""
    cliente = _ClienteFalso("mock")
    monkeypatch.setattr(demo_e2e.httpx, "Client", lambda **kwargs: cliente)

    with pytest.raises(_Escrita):
        demo_e2e.main()

    assert cliente.escritas == ["/v1/tenants"]
