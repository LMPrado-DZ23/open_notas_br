"""O benchmark em mock recusa rodar contra serviço real (§48).

A primeira execução do script foi para a **borda real** da SEFIN: `NFSE_ADAPTER` não estava
definido e o padrão do projeto é `sefin`. A requisição foi recusada com 403 (certificado
autoassinado) e nenhum documento foi emitido — mas o caminho existia, e agora não existe mais.
"""

from __future__ import annotations


class TestGuardaDoAdaptador:
    def test_recusa_quando_adaptador_e_real(self) -> None:
        from scripts.benchmark_mock import recusa_por_adaptador

        assert recusa_por_adaptador("sefin") is True

    def test_aceita_apenas_mock(self) -> None:
        from scripts.benchmark_mock import recusa_por_adaptador

        assert recusa_por_adaptador("mock") is False

    def test_importar_o_script_forca_mock_no_ambiente(self) -> None:
        """O import fixa `NFSE_ADAPTER=mock` antes de qualquer `app.*` ser importado."""
        import os

        from scripts import benchmark_mock  # noqa: F401  (o import é o efeito testado)

        assert os.environ["NFSE_ADAPTER"] == "mock"


class TestPercentil:
    def test_percentis_sao_ordenados_e_dentro_da_amostra(self) -> None:
        from scripts.benchmark_mock import _percentil

        amostras = [float(n) for n in range(1, 101)]  # 1..100
        p50, p95, p99 = (_percentil(amostras, p) for p in (50, 95, 99))
        assert 1.0 <= p50 <= p95 <= p99 <= 100.0

    def test_p95_de_amostra_pequena_e_o_maior_valor(self) -> None:
        from scripts.benchmark_mock import _percentil

        # Com 4 amostras, p95 cai no último posto — o comportamento de "posto mais próximo".
        assert _percentil([10.0, 20.0, 30.0, 40.0], 95) == 40.0

    def test_amostra_vazia_devolve_nan(self) -> None:
        from scripts.benchmark_mock import _percentil

        assert _percentil([], 95) != _percentil([], 95)  # NaN nunca é igual a si mesmo
