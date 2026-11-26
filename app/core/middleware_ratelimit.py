"""Middleware de rate limit por tenant.

Desligado por padrão (`rate_limit_habilitado=False`). Ligar por padrão mudaria o
comportamento de todas as rotas existentes de uma vez — o oposto de mudança pequena e
reversível. Quem quer ligar, liga na configuração.

A cota é por **tenant autenticado**, nunca por IP: NAT agrupa clientes distintos e proxy
distribui o mesmo cliente. Quando não há API key válida, cai para o IP — senão uma
requisição anônima ilimitada seria a porta de entrada.

Falha aberta: se o armazenamento do limitador falhar, a requisição **passa**. Em sistema
fiscal, ficar sem atender é pior que atender acima da cota por alguns segundos.
"""

from __future__ import annotations

import hashlib

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import Settings
from app.core.ratelimit import ArmazenamentoContagem, ArmazenamentoMemoria, Limitador

#: Rotas que não entram na cota: saúde e documentação precisam responder sempre.
ISENTAS = ("/health", "/ready", "/docs", "/openapi.json", "/redoc")


def _chave_do_pedido(request: Request) -> str:
    """Identifica o consumidor.

    Usa hash do prefixo da API key — o prefixo é público por desenho (identifica a chave
    sem revelá-la), então não serve como segredo aqui. Sem chave, cai para o IP.
    """
    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        # Só o prefixo: o hash do segredo ficaria exposto no storage do limitador.
        return f"key:{api_key[:8]}"
    host = request.client.host if request.client else "desconhecido"
    return f"ip:{hashlib.sha256(host.encode()).hexdigest()[:16]}"


class MiddlewareRateLimit(BaseHTTPMiddleware):
    """Aplica a cota e devolve 429 com os headers de autorregulação."""

    def __init__(
        self,
        app,
        *,
        settings: Settings,
        armazenamento: ArmazenamentoContagem | None = None,
    ) -> None:
        super().__init__(app)
        self._habilitado = settings.rate_limit_habilitado
        self._limitador = Limitador(
            armazenamento or ArmazenamentoMemoria(),
            limite=settings.rate_limit_por_minuto,
            janela_s=60,
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self._habilitado or request.url.path.startswith(ISENTAS):
            return await call_next(request)

        resultado = await self._limitador.verificar(_chave_do_pedido(request))
        if not resultado.permitido:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=429,
                content={
                    "type": "https://opennotas.dev/errors/rate-limit",
                    "title": "Cota de requisições excedida",
                    "status": 429,
                    "detail": (
                        f"limite de {resultado.limite} requisições por minuto por tenant; "
                        f"tente em {resultado.retry_after_s}s"
                    ),
                    "origem": "VALIDACAO",
                    "retryable": True,
                },
                headers=resultado.cabecalhos(),
                media_type="application/problem+json",
            )

        resposta = await call_next(request)
        for nome, valor in resultado.cabecalhos().items():
            resposta.headers[nome] = valor
        return resposta
