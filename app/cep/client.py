"""Consulta de CEP em fontes públicas, para autopreencher endereço no checkout.

Duas fontes gratuitas, sem chave, consultadas em ordem: **ViaCEP** (traz o código
IBGE, que é o que a nota fiscal precisa) e **BrasilAPI** como reserva.

Por que cache: CEP não muda. Um checkout que consulta o mesmo CEP a cada tecla
digita martela serviços públicos gratuitos e fica mais lento que responder da
memória. Acerto fica 30 dias em cache; "não encontrado" fica 5 minutos — corrigir
o CEP digitado precisa refletir rápido.

Degradação graciosa: se as duas fontes caírem, a resposta é 503 com instrução de
preencher o endereço à mão. O checkout **não** quebra por causa disso.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

VIACEP = "https://viacep.com.br/ws/{cep}/json/"
BRASILAPI = "https://brasilapi.com.br/api/cep/v2/{cep}"

TTL_ACERTO = 30 * 24 * 3600
TTL_NAO_ENCONTRADO = 300
USER_AGENT = "open_notas_br/0.2 (+https://github.com/LMPrado-DZ23/open_notas_br)"


class CepInvalido(Exception):
    """O CEP não tem 8 dígitos."""


class CepNaoEncontrado(Exception):
    """Nenhuma fonte conhece este CEP."""


class FonteIndisponivel(Exception):
    """Todas as fontes falharam — o endereço precisa ser digitado à mão."""


@dataclass(frozen=True, slots=True)
class Endereco:
    cep: str
    logradouro: str | None
    complemento: str | None
    bairro: str | None
    municipio: str | None
    uf: str | None
    codigo_ibge: str | None
    fonte: str

    def para_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalizar(cep: str) -> str:
    """Aceita `01001-000`, `01001000` e ` 01001000 `; devolve 8 dígitos."""
    digitos = re.sub(r"\D", "", str(cep or ""))
    if len(digitos) != 8:
        raise CepInvalido(f"CEP deve ter 8 dígitos; recebeu {cep!r}")
    return digitos


def _de_viacep(dados: dict[str, Any], cep: str) -> Endereco | None:
    if dados.get("erro") in ("true", True):
        return None
    return Endereco(
        cep=cep,
        logradouro=dados.get("logradouro") or None,
        complemento=dados.get("complemento") or None,
        bairro=dados.get("bairro") or None,
        municipio=dados.get("localidade") or None,
        uf=dados.get("uf") or None,
        codigo_ibge=dados.get("ibge") or None,
        fonte="viacep",
    )


def _de_brasilapi(dados: dict[str, Any], cep: str) -> Endereco | None:
    if not dados or not dados.get("city"):
        return None
    return Endereco(
        cep=cep,
        logradouro=dados.get("street") or None,
        complemento=dados.get("complement") or None,
        bairro=dados.get("neighborhood") or None,
        municipio=dados.get("city") or None,
        uf=dados.get("state") or None,
        # A BrasilAPI não devolve IBGE no CEP; o campo fica nulo e quem precisa do
        # código municipal (emissão) usa a consulta de CNPJ ou preenche depois.
        codigo_ibge=str(dados.get("city_ibge") or "") or None,
        fonte="brasilapi",
    )


async def consultar(cep: str, *, cliente: httpx.AsyncClient | None = None) -> Endereco:
    """Consulta o CEP nas fontes públicas, na ordem, com fallback."""
    normalizado = normalizar(cep)

    proprio = cliente is None
    http = cliente or httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT})
    falhas: list[str] = []

    try:
        try:
            resposta = await http.get(VIACEP.format(cep=normalizado))
            if resposta.status_code == 200:
                achado = _de_viacep(resposta.json(), normalizado)
                if achado is not None:
                    return achado
                falhas.append("viacep: CEP não encontrado")
            else:
                falhas.append(f"viacep: HTTP {resposta.status_code}")
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            falhas.append(f"viacep: {type(exc).__name__}")

        try:
            resposta = await http.get(BRASILAPI.format(cep=normalizado))
            if resposta.status_code == 200:
                achado = _de_brasilapi(resposta.json(), normalizado)
                if achado is not None:
                    return achado
                falhas.append("brasilapi: resposta sem município")
            elif resposta.status_code == 404:
                falhas.append("brasilapi: CEP não encontrado")
            else:
                falhas.append(f"brasilapi: HTTP {resposta.status_code}")
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            falhas.append(f"brasilapi: {type(exc).__name__}")
    finally:
        if proprio:
            await http.aclose()

    logger.info("cep_nao_resolvido", extra={"cep": normalizado, "falhas": falhas})

    # Se as duas fontes responderam "não existe", o CEP é inválido; se ao menos uma
    # caiu, não dá para afirmar — por isso a distinção.
    if all("não encontrado" in f or "sem município" in f for f in falhas) and falhas:
        raise CepNaoEncontrado(f"CEP {normalizado} não encontrado nas fontes públicas")
    raise FonteIndisponivel(
        "não foi possível consultar o CEP agora; preencha o endereço manualmente"
    )
