"""Mede a latência da parte síncrona da emissão **em mock**, dentro do processo.

O alvo de produto é p95 < 300 ms para a parte síncrona em mock. Este script mede isso de
verdade em vez de estimar, e imprime as condições junto com os números — sem elas, o número não
significa nada.

O que este número **é**: latência do caminho HTTP → validade de payload → assinatura XMLDSig →
adapter dublê → persistência, tudo em processo (ASGI em memória), no PostgreSQL local.
O que ele **não é**: tempo de autorização fiscal. Numa emissão real entram rede, mTLS, fila da
SEFAZ e o tempo do autorizador — nada disso está aqui, e é por isso que o alvo é declarado só para
mock.

Uso (com o PostgreSQL de teste no ar, `docker compose up -d postgres`):

    python -m scripts.benchmark_mock [--n 50] [--warmup 5]

O banco usado é o de **teste** (`tests.suporte`), e as tabelas são limpas antes: rodar isto não toca
o banco de desenvolvimento.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time

# Ambiente precisa ser definido ANTES de importar `app.*`: a configuração é lida no import.
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_JSON"] = "false"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ.setdefault("MASTER_ENCRYPTION_KEY", "")
# Sem esta linha o padrão do projeto é `sefin`: a primeira execução deste script foi para a
# **borda real** da SEFIN (recusada com 403 por certificado autoassinado, sem emitir nada).
# Benchmark em mock não pode, em hipótese alguma, falar com autorizador.
os.environ["NFSE_ADAPTER"] = "mock"


def recusa_por_adaptador(adaptador: str) -> bool:
    """True quando o adaptador configurado **não** é o dublê.

    Existe como função pura para poder ser testada: o `_executar` aplica a decisão e aborta.
    A primeira execução deste script (antes desta guarda) foi para a **borda real** da SEFIN,
    porque `NFSE_ADAPTER` não estava definido e o padrão do projeto é `sefin`.
    """
    return adaptador != "mock"


def _preparar_ambiente() -> None:
    from tests import suporte

    if not suporte.banco_disponivel():
        raise SystemExit(
            f"PostgreSQL indisponível em {suporte.url_admin()!r}. "
            "Suba com `docker compose up -d postgres`."
        )
    suporte.provisionar_banco()
    asyncio.run(suporte.limpar_tabelas(suporte.url_teste()))
    os.environ["DATABASE_URL"] = suporte.url_teste()


def _percentil(amostras: list[float], p: float) -> float:
    """Percentil por posto mais próximo (sem interpolação) — amostra pequena e honesta."""
    if not amostras:
        return float("nan")
    ordenadas = sorted(amostras)
    indice = min(len(ordenadas) - 1, max(0, round(p / 100 * (len(ordenadas) - 1))))
    return ordenadas[indice]


async def _executar(n: int, aquecimento: int) -> int:
    from app.core.config import get_settings
    from app.main import criar_app
    from httpx import ASGITransport, AsyncClient
    from tests.test_fase2_certificado import SENHA, gerar_pfx

    # Guarda dura: se o adaptador não for o dublê, este script não roda. Um benchmark que
    # emite de verdade não é benchmark — é emissão fiscal sem autorização.
    adaptador = get_settings().nfse_adapter
    if recusa_por_adaptador(adaptador):
        print(
            f"recusando rodar: NFSE_ADAPTER={adaptador!r}; este script mede apenas em mock",
            file=sys.stderr,
        )
        return 2

    app = criar_app()
    transporte = ASGITransport(app=app)

    async with AsyncClient(transport=transporte, base_url="http://bench") as http:
        criado = await http.post("/v1/tenants", json={"slug": "bench", "nome": "Bench LTDA"})
        if criado.status_code != 201:
            print(f"falha ao criar tenant: {criado.status_code} {criado.text}", file=sys.stderr)
            return 2
        cabecalho = {"X-API-Key": criado.json()["api_key"]}

        config = await http.put(
            "/v1/me/config-fiscal",
            json={
                "municipio_ibge": "3550308",
                "uf": "SP",
                "ambiente": "homologacao",
                "codigo_tributacao_nacional": "010701",
                "serie_dps": "1",
                "aliquota_iss": 0.05,
            },
            headers=cabecalho,
        )
        if config.status_code >= 300:
            print(f"falha na config fiscal: {config.status_code} {config.text}", file=sys.stderr)
            return 2

        certificado = await http.post(
            "/v1/me/certificados",
            files={"arquivo": ("bench.pfx", gerar_pfx(), "application/x-pkcs12")},
            data={"senha": SENHA.decode(), "apelido": "bench"},
            headers=cabecalho,
        )
        if certificado.status_code >= 300:
            print(f"falha no certificado: {certificado.status_code}", file=sys.stderr)
            return 2

        async def emitir(indice: int) -> float:
            inicio = time.perf_counter()
            resposta = await http.post(
                "/v1/emissoes",
                json={
                    "idempotency_key": f"bench-{indice:06d}",
                    "valor": "100.00",
                    "descricao": "Servico prestado",
                    "competencia": "2026-11",
                },
                headers=cabecalho,
            )
            decorrido = (time.perf_counter() - inicio) * 1000
            if resposta.status_code >= 300:
                raise RuntimeError(f"emissao {indice}: {resposta.status_code} {resposta.text}")
            return decorrido

        for indice in range(aquecimento):
            await emitir(1_000_000 + indice)

        amostras = [await emitir(indice) for indice in range(n)]

    p50 = statistics.median(amostras)
    p95 = _percentil(amostras, 95)
    p99 = _percentil(amostras, 99)
    print(
        f"n={len(amostras)}  p50={p50:.1f}ms  p95={p95:.1f}ms  p99={p99:.1f}ms  "
        f"max={max(amostras):.1f}ms  min={min(amostras):.1f}ms"
    )
    print(
        "condicoes: NFSE_ADAPTER=mock, ASGI em processo (sem rede), PostgreSQL local, "
        "assinatura XMLDSig real com A1 autoassinado, 1 processo"
    )
    print("isto NAO e tempo de autorizacao fiscal: numa emissao real entram rede, mTLS e a SEFAZ")
    if p95 > 300:
        print(f"ALVO NAO ATINGIDO: p95 {p95:.1f}ms > 300ms (alvo de produto para mock)")
        return 1
    print(f"alvo de produto atingido: p95 {p95:.1f}ms <= 300ms")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=50, help="emissões medidas (padrão 50)")
    parser.add_argument("--warmup", type=int, default=5, help="emissões descartadas (padrão 5)")
    args = parser.parse_args(argv)

    _preparar_ambiente()
    return asyncio.run(_executar(args.n, args.warmup))


if __name__ == "__main__":
    raise SystemExit(main())
