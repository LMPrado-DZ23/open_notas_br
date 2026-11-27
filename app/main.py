"""Aplicação FastAPI.

Pontos de projeto que importam em produção:

1. **A chave-mestra é validada na inicialização.** Se `ENVIRONMENT=production` e
   `MASTER_ENCRYPTION_KEY` estiver ausente ou malformada, a aplicação não sobe.
   Falhar no boot é melhor que falhar no meio de uma emissão fiscal.
2. **`/health` é readiness, `/health/live` é liveness.** Orquestrador precisa
   distinguir "processo vivo" de "pronto para tráfego".
3. **Toda resposta carrega `X-Request-ID`.** Sem isso, correlacionar log de
   emissão com a requisição do parceiro é adivinhação.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1 import health
from app.api.v1.router import router as v1_router
from app.core.circuit import CircuitoAberto
from app.core.config import get_settings, validar_ambiente_de_execucao
from app.core.errors import de_http_exception
from app.core.logging import configurar_logging
from app.core.redis import fechar_redis
from app.db.session import dispose_engine
from app.versao import APP_VERSION

logger = logging.getLogger(__name__)

DESCRICAO = """
Motor e microserviço de **documentos fiscais brasileiros**.

Cobre emissão e gestão de NFS-e (padrão nacional), geração local de DANFSe,
apuração de tributos com guias plugáveis e entrega de webhook assinada.

## Isolamento multi-tenant

Toda rota de recurso fiscal exige o header `X-API-Key`. O `tenant_id` é derivado
**exclusivamente** da credencial: nunca de corpo ou query. Uma credencial de um
tenant não alcança dados de outro.

## Estado de prontidão

As integrações com SEFIN/ADN, prefeitura e Serpro são implementadas sobre
adapters com URL base vinda de configuração. Os trechos que dependem de
documentação oficial não verificada estão marcados como **[A VALIDAR]** no
código, no `docs/REFERENCIAS.md` e no README. Nada aqui substitui homologação
oficial.
"""

TAGS_METADATA = [
    {"name": "meta", "description": "Saúde, versão e metadados do serviço."},
    {"name": "tenants", "description": "Contas, credenciais e configuração fiscal."},
]

HTTP_500 = 500


class MiddlewareRequisicao(BaseHTTPMiddleware):
    """Adiciona `X-Request-ID`, mede duração e registra a requisição."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        inicio = time.perf_counter()
        try:
            resposta = await call_next(request)
        except Exception:
            duracao = (time.perf_counter() - inicio) * 1000
            logger.exception(
                "requisicao_falhou",
                extra={
                    "request_id": request_id,
                    "metodo": request.method,
                    "rota": request.url.path,
                    "duracao_ms": round(duracao, 2),
                },
            )
            raise
        duracao = (time.perf_counter() - inicio) * 1000
        resposta.headers["X-Request-ID"] = request_id
        logger.info(
            "requisicao",
            extra={
                "request_id": request_id,
                "metodo": request.method,
                "rota": request.url.path,
                "status": resposta.status_code,
                "duracao_ms": round(duracao, 2),
            },
        )
        _observar_metrica(request, resposta.status_code, duracao / 1000)
        return resposta


def _observar_metrica(request: Request, status: int, segundos: float) -> None:
    """Contabiliza a requisição **sem** abrir cardinalidade.

    O rótulo é o template da rota (`/v1/emissoes/{invoice_id}`), nunca o caminho cru: um label
    por UUID cresce sem limite e derruba o scraper. Sem template, o rótulo é `desconhecida`.
    O próprio `/metrics` fica fora da conta, senão cada scrape polui a série.
    """
    from app.core.metrics import ROTA_DESCONHECIDA, registro

    caminho = request.url.path
    if caminho == "/metrics":
        return
    rota = getattr(request.scope.get("route"), "path", None) or ROTA_DESCONHECIDA
    registro.observar(metodo=request.method, rota=rota, status=status, segundos=segundos)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Inicialização e encerramento do processo."""
    settings = get_settings()
    configurar_logging(settings.log_level, json_output=settings.log_json)

    # Falha alto: em produção, sem chave-mestra não há cofre de certificados.
    settings.master_key()

    if settings.is_production and not settings.admin_api_token.strip():
        logger.warning(
            "admin_api_token_ausente",
            extra={"efeito": "rotas administrativas responderao 503"},
        )

    logger.info(
        "servico_iniciado",
        extra={"versao": APP_VERSION, "ambiente": settings.environment},
    )
    try:
        yield
    finally:
        await dispose_engine()
        await fechar_redis()
        logger.info("servico_encerrado")


def criar_app() -> FastAPI:
    """Fábrica da aplicação (testável e reutilizável)."""
    settings = get_settings()

    validar_ambiente_de_execucao(get_settings())

    app = FastAPI(
        title="open_notas_br",
        version=APP_VERSION,
        description=DESCRICAO,
        openapi_tags=TAGS_METADATA,
        license_info={"name": "MIT"},
        lifespan=lifespan,
    )

    app.add_middleware(MiddlewareRequisicao)

    origens = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origens,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # Health no root (usado pelo healthcheck do container) e também sob /v1.
    app.include_router(health.router)
    app.include_router(v1_router, prefix="/v1")

    @app.get("/metrics", include_in_schema=False, tags=["meta"])
    async def metricas() -> Response:
        """Exposição no formato do Prometheus (text/plain; version=0.0.4).

        Fora do OpenAPI (`include_in_schema=False`): não é contrato de integração de cliente,
        é superfície de scraping. Sem rótulo de tenant e com rota em template — ver
        `app/core/metrics.py`.
        """
        from app.core.metrics import FAIXAS_SEGUNDOS, registro
        from app.core.redis import obter_redis
        from app.nfse.resiliencia import registro_padrao
        from app.worker.main import CHAVE_HEARTBEAT

        corpo = registro.renderizar()

        # Batimento do worker como gauge 0/1: permite alertar "worker parado" sem polling.
        try:
            vivo = 1 if await obter_redis().get(CHAVE_HEARTBEAT) else 0
        except Exception:  # Redis fora já aparece na série de requisições e em /health
            vivo = 0
        corpo += "# HELP opennotas_worker_batimento 1 se o worker escreveu batimento recente.\n"
        corpo += "# TYPE opennotas_worker_batimento gauge\n"
        corpo += f"opennotas_worker_batimento {vivo}\n"

        # Estado dos circuitos: cardinalidade limitada por (operação x autorizador), nunca por
        # tenant. Lista vazia = nada foi chamado ainda, não "tudo saudável".
        from app.api.v1.observabilidade import CODIGO_DO_ESTADO
        from app.core.circuit import Estado

        corpo += "# HELP opennotas_circuito_estado Estado do circuito (0 fechado, 1 meio-aberto, 2 aberto).\n"
        corpo += "# TYPE opennotas_circuito_estado gauge\n"
        for nome, estado in sorted(registro_padrao.estados().items()):
            corpo += f'opennotas_circuito_estado{{circuito="{nome}"}} {CODIGO_DO_ESTADO[Estado(estado)]}\n'

        # Faixas expostas como comentário: o bucket é contrato do histograma, e quem consulta
        # precisa saber os limites sem abrir o código.
        corpo += f"# faixas_segundos {','.join(f'{f:g}' for f in FAIXAS_SEGUNDOS)}\n"

        return Response(content=corpo, media_type="text/plain; version=0.0.4; charset=utf-8")

    @app.exception_handler(CircuitoAberto)
    async def _circuito_aberto(request: Request, exc: CircuitoAberto) -> JSONResponse:
        """Serviço externo fora do ar: 503 com `Retry-After`, não 500.

        500 diz "erro do servidor" e o cliente tende a tentar de novo imediatamente, o
        que piora a fila. 503 + `Retry-After` diz o que fazer: espere.
        """
        return JSONResponse(
            status_code=503,
            content={
                "type": "https://opennotas.dev/errors/circuito-aberto",
                "title": "Serviço fiscal indisponível",
                "status": 503,
                "detail": (
                    "o autorizador está com o circuito aberto após falhas consecutivas; "
                    f"tente em {exc.retry_after_s:.0f}s"
                ),
                "origem": "SEFAZ",
                "retryable": True,
            },
            headers={"Retry-After": str(max(1, int(exc.retry_after_s)))},
            media_type="application/problem+json",
        )

    @app.exception_handler(StarletteHTTPException)
    async def _erro_rfc7807(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Erros HTTP no formato RFC 7807, sem quebrar contrato existente.

        O corpo ganha `type`/`title`/`origem`/`retryable`, mas **mantém `detail`**:
        todo cliente que já lê `{"detail": ...}` continua funcionando. O status
        também é preservado — mudar status seria breaking change (P5).

        Os headers originais são repassados: `WWW-Authenticate`, `Retry-After` e
        `Allow` carregam informação que o cliente precisa (ex.: 405 e 429).
        """
        problema = de_http_exception(exc.status_code, exc.detail).para_dict()
        return JSONResponse(
            status_code=exc.status_code,
            content=problema,
            headers=dict(exc.headers or {}),
            media_type="application/problem+json",
        )

    return app


app = criar_app()
