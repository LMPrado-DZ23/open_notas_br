"""Consulta de CNPJ em fontes plugáveis.

Fontes implementadas, todas verificadas por chamada real nesta máquina
(`docs/REFERENCIAS.md`, seção 8):

| Fonte | Autenticação | Resposta observada |
|---|---|---|
| BrasilAPI | nenhuma | HTTP 200 em ~0,37 s, cadastro completo |
| MinhaReceita | nenhuma | HTTP 200 em ~0,39 s, mesmos campos |
| Serpro | token (cota paga) | [A VALIDAR] — caminho não exercitado |

Descoberta relevante: as fontes públicas **não resolvem CNPJ alfanumérico** —
a BrasilAPI responde 404 com `"CNPJ ... não encontrado"`. Isso não é "CNPJ
inválido": é ausência na fonte. O serviço distingue os dois casos, senão o
usuário troca o documento achando que digitou errado.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from notasbr.cadastros import cnpj_alfanumerico, cnpj_valido, normalizar_cnpj

logger = logging.getLogger(__name__)


class ErroConsultaCnpj(Exception):
    """Base dos erros de consulta."""


class CnpjNaoEncontrado(ErroConsultaCnpj):
    """A fonte respondeu que não conhece este CNPJ."""


class FonteIndisponivel(ErroConsultaCnpj):
    """A fonte falhou (rede, 5xx, 429). Pode funcionar depois."""


class CnpjInvalido(ErroConsultaCnpj):
    """O valor não passa na validação de forma."""


@dataclass(slots=True)
class DadosCnpj:
    """Cadastro normalizado, independente da fonte."""

    cnpj: str
    razao_social: str | None = None
    nome_fantasia: str | None = None
    situacao_cadastral: str | None = None
    descricao_situacao: str | None = None
    uf: str | None = None
    municipio: str | None = None
    codigo_municipio_ibge: str | None = None
    cnae_fiscal: str | None = None
    cnae_descricao: str | None = None
    natureza_juridica: str | None = None
    data_inicio_atividade: str | None = None
    opcao_simples: bool | None = None
    opcao_mei: bool | None = None
    email: str | None = None
    telefone: str | None = None
    fonte: str = "desconhecida"

    def to_dict(self) -> dict[str, Any]:
        return {
            "cnpj": self.cnpj,
            "razao_social": self.razao_social,
            "nome_fantasia": self.nome_fantasia,
            "situacao_cadastral": self.situacao_cadastral,
            "descricao_situacao": self.descricao_situacao,
            "uf": self.uf,
            "municipio": self.municipio,
            "codigo_municipio_ibge": self.codigo_municipio_ibge,
            "cnae_fiscal": self.cnae_fiscal,
            "cnae_descricao": self.cnae_descricao,
            "natureza_juridica": self.natureza_juridica,
            "data_inicio_atividade": self.data_inicio_atividade,
            "opcao_simples": self.opcao_simples,
            "opcao_mei": self.opcao_mei,
            "email": self.email,
            "telefone": self.telefone,
            "fonte": self.fonte,
        }


@runtime_checkable
class ConsultaCnpj(Protocol):
    """Contrato de uma fonte de CNPJ."""

    nome: str

    async def consultar(self, cnpj: str) -> DadosCnpj: ...


def _normalizar(dados: dict[str, Any], *, cnpj: str, fonte: str) -> DadosCnpj:
    """Converte a resposta (BrasilAPI/MinhaReceita compartilham campos) no modelo."""
    telefone = None
    ddd = dados.get("ddd_telefone_1")
    if ddd:
        telefone = str(ddd)

    return DadosCnpj(
        cnpj=cnpj,
        razao_social=dados.get("razao_social"),
        nome_fantasia=dados.get("nome_fantasia"),
        situacao_cadastral=str(dados["situacao_cadastral"])
        if dados.get("situacao_cadastral") is not None
        else None,
        descricao_situacao=dados.get("descricao_situacao_cadastral"),
        uf=dados.get("uf"),
        municipio=dados.get("municipio"),
        codigo_municipio_ibge=str(dados["codigo_municipio_ibge"])
        if dados.get("codigo_municipio_ibge") is not None
        else None,
        cnae_fiscal=str(dados["cnae_fiscal"]) if dados.get("cnae_fiscal") is not None else None,
        cnae_descricao=dados.get("cnae_fiscal_descricao"),
        natureza_juridica=dados.get("natureza_juridica"),
        data_inicio_atividade=dados.get("data_inicio_atividade"),
        opcao_simples=dados.get("opcao_pelo_simples"),
        opcao_mei=dados.get("opcao_pelo_mei"),
        email=dados.get("email"),
        telefone=telefone,
        fonte=fonte,
    )


async def _buscar_json(
    cliente: httpx.AsyncClient, url: str, *, fonte: str, cabecalhos: dict[str, str] | None = None
) -> dict[str, Any]:
    """Faz a requisição e traduz o status HTTP em erro de domínio."""
    try:
        resposta = await cliente.get(url, headers=cabecalhos)
    except httpx.HTTPError as exc:
        raise FonteIndisponivel(f"{fonte}: falha de rede ({type(exc).__name__})") from exc

    if resposta.status_code == 404:
        raise CnpjNaoEncontrado(f"{fonte}: CNPJ não encontrado")
    if resposta.status_code == 429:
        raise FonteIndisponivel(f"{fonte}: limite de requisições atingido (429)")
    if resposta.status_code >= 500:
        raise FonteIndisponivel(f"{fonte}: serviço indisponível (HTTP {resposta.status_code})")
    if resposta.status_code != 200:
        raise FonteIndisponivel(f"{fonte}: resposta inesperada (HTTP {resposta.status_code})")

    try:
        return resposta.json()
    except ValueError as exc:
        raise FonteIndisponivel(f"{fonte}: resposta não é JSON") from exc


class BrasilApiCnpj:
    """Fonte pública sem autenticação. Verificada por chamada real."""

    nome = "brasilapi"

    def __init__(
        self,
        *,
        base_url: str = "https://brasilapi.com.br/api/cnpj/v1",
        timeout: float = 8.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    async def consultar(self, cnpj: str) -> DadosCnpj:
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self.transport, follow_redirects=False
        ) as cliente:
            dados = await _buscar_json(
                cliente, f"{self.base_url}/{normalizar_cnpj(cnpj)}", fonte=self.nome
            )
        return _normalizar(dados, cnpj=normalizar_cnpj(cnpj), fonte=self.nome)


class MinhaReceitaCnpj:
    """Fonte pública alternativa (mesmo formato de campos)."""

    nome = "minhareceita"

    def __init__(
        self,
        *,
        base_url: str = "https://minhareceita.org",
        timeout: float = 8.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    async def consultar(self, cnpj: str) -> DadosCnpj:
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self.transport, follow_redirects=False
        ) as cliente:
            dados = await _buscar_json(
                cliente, f"{self.base_url}/{normalizar_cnpj(cnpj)}", fonte=self.nome
            )
        return _normalizar(dados, cnpj=normalizar_cnpj(cnpj), fonte=self.nome)


class SerproCnpj:
    """Fonte oficial da Serpro (cota gratuita e depois paga).

    **[A VALIDAR]** O caminho exato depende da contratação do produto
    (`consulta-cnpj-df-v1`). O que está implementado: ``GET {base}/{cnpj}`` com
    ``Authorization: Bearer {token}``, que é o padrão do gateway da Serpro. Sem
    token, esta fonte não é chamada.
    """

    nome = "serpro"

    def __init__(
        self,
        *,
        token: str,
        base_url: str = "https://gateway.apiserpro.serpro.gov.br/consulta-cnpj-df-v1",
        timeout: float = 8.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    async def consultar(self, cnpj: str) -> DadosCnpj:
        if not self.token:
            raise FonteIndisponivel("serpro: token não configurado")
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self.transport, follow_redirects=False
        ) as cliente:
            dados = await _buscar_json(
                cliente,
                f"{self.base_url}/{normalizar_cnpj(cnpj)}",
                fonte=self.nome,
                cabecalhos={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
            )
        # A Serpro devolve o cadastro aninhado em alguns produtos.
        corpo = dados.get("ni") or dados.get("cnpj") or dados
        normalizado = corpo if isinstance(corpo, dict) else dados
        return _normalizar(normalizado, cnpj=normalizar_cnpj(cnpj), fonte=self.nome)


def validar_entrada(cnpj: str) -> str:
    """Valida a forma do CNPJ e devolve o valor normalizado.

    Aceita alfanumérico (IN RFB 2.229/2024). Rejeitar aqui evita gastar cota com
    valor que nenhuma fonte vai conhecer.
    """
    normalizado = normalizar_cnpj(cnpj)
    if len(normalizado) != 14:
        raise CnpjInvalido(f"CNPJ deve ter 14 posições; recebeu {len(normalizado)}")
    if not cnpj_valido(normalizado):
        raise CnpjInvalido("CNPJ com dígito verificador inválido")
    return normalizado


def eh_alfanumerico(cnpj: str) -> bool:
    return cnpj_alfanumerico(cnpj)
