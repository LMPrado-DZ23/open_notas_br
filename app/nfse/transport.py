"""Transporte HTTP da SEFIN/ADN: mTLS, gzip+base64 e tradução de falha.

O payload que a SEFIN espera é XML comprimido com gzip e codificado em base64,
dentro de um JSON. Isso não é otimização prematura: é o contrato. `gzip_b64` e
`ungzip_b64` existem para que nenhuma camada acima precise repetir a receita.
"""

from __future__ import annotations

import base64
import gzip
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.certificates.cofre import CertificadoA1
from app.nfse.constants import host_permitido
from app.nfse.errors import ErroSefin, TipoErroFiscal, extrair_mensagens
from app.versao import APP_VERSION

logger = logging.getLogger(__name__)

#: A SEFIN é lenta por natureza (processa e devolve o XML completo).
TIMEOUT_CONEXAO = 15.0
TIMEOUT_LEITURA = 90.0
#: Consulta de apoio: se demorar, quem chamou segue sem ela.
TIMEOUT_CONSULTA = httpx.Timeout(8.0, connect=4.0)

USER_AGENT = f"notasbr/{APP_VERSION}"

_NAO_AUTENTICADO = frozenset({401, 403, 495, 496, 497})
_SOBRECARGA = frozenset({429, 503})


def gzip_b64(dados: bytes) -> str:
    """Comprime com gzip e codifica em base64 (formato dos campos `*GZipB64`)."""
    return base64.b64encode(gzip.compress(dados, mtime=0)).decode("ascii")


def ungzip_b64(valor: str) -> bytes:
    """Decodifica base64 e descomprime gzip.

    Levanta :class:`ErroSefin` de resposta inválida se o campo não for base64/gzip.
    """
    try:
        return gzip.decompress(base64.b64decode(valor))
    except Exception as exc:
        raise ErroSefin(
            TipoErroFiscal.RESPOSTA_INVALIDA,
            "a resposta da SEFIN trouxe um campo comprimido ilegível",
            [],
        ) from exc


@dataclass(slots=True)
class ResultadoHTTP:
    """Resposta HTTP já lida, com o tempo gasto."""

    status_code: int
    json: Any
    texto: str
    duracao_ms: float


def criar_cliente(
    certificado: CertificadoA1 | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    timeout_leitura: float = TIMEOUT_LEITURA,
) -> httpx.Client:
    """Cria o cliente HTTP da SEFIN.

    Com certificado, usa mTLS. Sem certificado e sem `transport`, ainda cria o
    cliente — mas qualquer chamada real falhará na autenticação, e o erro será
    reportado como tal, não como "serviço fora do ar".
    """
    kwargs: dict[str, Any] = {
        "timeout": httpx.Timeout(timeout_leitura, connect=TIMEOUT_CONEXAO),
        "headers": {"Accept": "application/json", "User-Agent": USER_AGENT},
        "follow_redirects": False,
    }
    if transport is not None:
        kwargs["transport"] = transport
    elif certificado is not None:
        kwargs["verify"] = certificado.ssl_context()
    return httpx.Client(**kwargs)


def verificar_destino(url: str, *, permitir_override: bool = False) -> None:
    """Recusa enviar para host que não seja oficial.

    Protege contra variável de ambiente mal configurada: DPS assinada não sai para
    servidor desconhecido.
    """
    if not host_permitido(url, permitir_override=permitir_override):
        raise ErroSefin(
            TipoErroFiscal.VALIDACAO_LOCAL,
            f"host não permitido para comunicação oficial: {url}",
        )


def executar(
    cliente: httpx.Client,
    metodo: str,
    url: str,
    *,
    operacao: str,
    pode_ser_ambigua: bool = False,
    permitir_override: bool = False,
    **kwargs: Any,
) -> ResultadoHTTP:
    """Executa a requisição e converte falha de transporte em `ErroSefin`.

    `pode_ser_ambigua` marca operações que **criam** algo (emissão, evento): se a
    conexão cair depois do envio, o documento pode ter sido gerado, e o chamador
    precisa consultar antes de reenviar.
    """
    verificar_destino(url, permitir_override=permitir_override)

    inicio = time.perf_counter()
    try:
        resposta = cliente.request(metodo, url, **kwargs)
    except httpx.ConnectTimeout as exc:
        _log(operacao, metodo, url, inicio, "connect_timeout")
        raise ErroSefin(TipoErroFiscal.INDISPONIVEL, "tempo esgotado ao conectar na SEFIN") from exc
    except httpx.ConnectError as exc:
        _log(operacao, metodo, url, inicio, "connect_error")
        texto = str(exc).lower()
        if any(marca in texto for marca in ("certificate", "handshake", "ssl", "tls")):
            raise ErroSefin(
                TipoErroFiscal.AUTENTICACAO,
                "falha no aperto de mão TLS: certificado recusado ou cadeia inválida",
                extrair_mensagens(str(exc)),
            ) from exc
        raise ErroSefin(
            TipoErroFiscal.INDISPONIVEL,
            "não foi possível conectar na SEFIN (rede ou serviço fora do ar)",
            extrair_mensagens(str(exc)),
        ) from exc
    except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError) as exc:
        _log(operacao, metodo, url, inicio, "timeout_leitura")
        tipo = TipoErroFiscal.AMBIGUO if pode_ser_ambigua else TipoErroFiscal.INDISPONIVEL
        complemento = (
            " — o documento pode ter sido gerado; consulte antes de reenviar"
            if pode_ser_ambigua
            else ""
        )
        raise ErroSefin(
            tipo,
            f"a conexão caiu antes da resposta{complemento}",
            extrair_mensagens(f"{type(exc).__name__}: {exc}"),
        ) from exc

    duracao = (time.perf_counter() - inicio) * 1000
    texto = resposta.text
    try:
        corpo = resposta.json()
    except ValueError:
        corpo = None

    logger.info(
        "sefin_chamada",
        extra={
            "operacao": operacao,
            "metodo": metodo,
            "url": url,
            "status": resposta.status_code,
            "duracao_ms": round(duracao, 2),
        },
    )
    return ResultadoHTTP(resposta.status_code, corpo, texto, duracao)


def erro_http(resultado: ResultadoHTTP, resumo: str, *, ambiente: str | None = None) -> ErroSefin:
    """Classifica uma resposta de erro e monta o `ErroSefin` correspondente."""
    status = resultado.status_code
    mensagens = extrair_mensagens(resultado.json) or extrair_mensagens(resultado.texto)

    if status in _NAO_AUTENTICADO:
        tipo = TipoErroFiscal.AUTENTICACAO
    elif status in _SOBRECARGA or status >= 500:
        tipo = TipoErroFiscal.INDISPONIVEL
    else:
        tipo = TipoErroFiscal.REJEICAO

    return ErroSefin(
        tipo,
        resumo,
        mensagens,
        http_status=status,
        corpo=resultado.texto[:2000] if resultado.texto else None,
        ambiente=ambiente,
    )


def _log(operacao: str, metodo: str, url: str, inicio: float, motivo: str) -> None:
    logger.warning(
        "sefin_falha_transporte",
        extra={
            "operacao": operacao,
            "metodo": metodo,
            "url": url,
            "motivo": motivo,
            "duracao_ms": round((time.perf_counter() - inicio) * 1000, 2),
        },
    )
