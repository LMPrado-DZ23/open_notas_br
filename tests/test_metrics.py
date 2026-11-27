"""`/metrics` em formato Prometheus, sem dependência (§51).

O que estes testes precisam provar, além de "o endpoint responde":

1. o **formato** é o de exposição do Prometheus (HELP/TYPE, contador cumulativo, `+Inf`);
2. a **cardinalidade não explode**: o rótulo de rota é o template, nunca o caminho com UUID;
3. **nenhum rótulo de tenant** aparece — métrica é infraestrutura, não dado de cliente;
4. o próprio `/metrics` não entra na contagem.
"""

from __future__ import annotations

import pytest
from app.core.metrics import FAIXAS_SEGUNDOS, ROTA_DESCONHECIDA, Registro


@pytest.fixture(autouse=True)
def _registro_limpo():
    from app.core.metrics import registro

    registro.limpar()
    yield
    registro.limpar()


class TestFormato:
    def test_renderiza_help_type_e_amostra(self) -> None:
        registro = Registro()
        registro.observar(metodo="get", rota="/v1/emissoes", status=201, segundos=0.12)

        texto = registro.renderizar()

        assert "# HELP opennotas_http_requisicoes_total" in texto
        assert "# TYPE opennotas_http_requisicoes_total counter" in texto
        assert "# TYPE opennotas_http_duracao_segundos histogram" in texto
        # Método em maiúsculas, rótulos ordenados e valor inteiro no contador.
        assert (
            'opennotas_http_requisicoes_total{metodo="GET",rota="/v1/emissoes",status="201"} 1'
            in texto
        )

    def test_histograma_e_cumulativo_e_fecha_em_inf(self) -> None:
        registro = Registro()
        # 0,12 s cai depois da faixa de 0,1 e antes da de 0,2.
        registro.observar(metodo="GET", rota="/x", status=200, segundos=0.12)

        texto = registro.renderizar()
        linha = (
            'opennotas_http_duracao_segundos_bucket{metodo="GET",rota="/x",status="200",le="0.1"} 0'
        )
        assert linha in texto
        assert (
            'opennotas_http_duracao_segundos_bucket{metodo="GET",rota="/x",status="200",le="0.2"} 1'
            in texto
        )
        assert (
            'opennotas_http_duracao_segundos_bucket{metodo="GET",rota="/x",status="200",le="+Inf"} 1'
            in texto
        )
        assert (
            'opennotas_http_duracao_segundos_count{metodo="GET",rota="/x",status="200"} 1' in texto
        )

    def test_soma_e_contador_por_serie(self) -> None:
        registro = Registro()
        registro.observar(metodo="GET", rota="/x", status=200, segundos=0.1)
        registro.observar(metodo="GET", rota="/x", status=200, segundos=0.3)

        texto = registro.renderizar()
        assert 'opennotas_http_requisicoes_total{metodo="GET",rota="/x",status="200"} 2' in texto
        assert (
            'opennotas_http_duracao_segundos_count{metodo="GET",rota="/x",status="200"} 2' in texto
        )
        assert (
            'opennotas_http_duracao_segundos_sum{metodo="GET",rota="/x",status="200"} 0.4' in texto
        )

    def test_faixas_sao_crescentes(self) -> None:
        assert list(FAIXAS_SEGUNDOS) == sorted(FAIXAS_SEGUNDOS)


class TestCardinalidade:
    def test_rota_vazia_vira_desconhecida(self) -> None:
        registro = Registro()
        registro.observar(metodo="GET", rota="", status=404, segundos=0.01)
        assert f'rota="{ROTA_DESCONHECIDA}"' in registro.renderizar()

    def test_dois_ids_da_mesma_rota_nao_criam_duas_series(self) -> None:
        registro = Registro()
        registro.observar(metodo="GET", rota="/v1/emissoes/{invoice_id}", status=200, segundos=0.1)
        registro.observar(metodo="GET", rota="/v1/emissoes/{invoice_id}", status=200, segundos=0.1)

        assert len(registro.series()) == 1

    def test_nenhum_rotulo_de_tenant(self) -> None:
        registro = Registro()
        registro.observar(metodo="POST", rota="/v1/emissoes", status=201, segundos=0.2)
        texto = registro.renderizar().lower()
        for proibido in ("tenant", "cnpj", "cpf", "api_key", "chave"):
            assert proibido not in texto, f"rotulo proibido em metrica: {proibido}"


class TestEndpoint:
    async def test_metrics_responde_texto_prometheus(self, cliente) -> None:
        resposta = await cliente.get("/metrics")

        assert resposta.status_code == 200
        assert resposta.headers["content-type"].startswith("text/plain")
        corpo = resposta.text
        assert "opennotas_worker_batimento" in corpo
        assert "# TYPE opennotas_circuito_estado gauge" in corpo

    async def test_requisicao_anterior_aparece_na_serie(self, cliente) -> None:
        await cliente.get("/health/live")

        corpo = (await cliente.get("/metrics")).text

        assert 'rota="/health/live"' in corpo, corpo[:400]
        assert 'metodo="GET"' in corpo

    async def test_o_proprio_metrics_nao_e_contado(self, cliente) -> None:
        await cliente.get("/metrics")
        await cliente.get("/metrics")

        corpo = (await cliente.get("/metrics")).text

        assert 'rota="/metrics"' not in corpo

    def test_metrics_fora_do_openapi(self) -> None:
        from app.main import criar_app

        assert "/metrics" not in criar_app().openapi()["paths"]
