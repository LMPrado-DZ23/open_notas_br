"""Circuit breaker: estados, contagem de falha e recuperação."""

from __future__ import annotations

import pytest
from app.core.circuit import CircuitBreaker, Estado


class Relogio:
    def __init__(self) -> None:
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora


def breaker(**extra) -> tuple[CircuitBreaker, Relogio]:
    relogio = Relogio()
    config = dict(nome="sefaz-52", limite_falhas=3, espera_s=30.0)
    config.update(extra)
    cb = CircuitBreaker(**config)
    cb._relogio = relogio
    return cb, relogio


class TestFechado:
    def test_comeca_fechado_e_permite(self) -> None:
        cb, _ = breaker()
        assert cb.estado is Estado.FECHADO
        assert cb.permite() is True

    def test_sucesso_zera_contagem(self) -> None:
        cb, _ = breaker()
        cb.registrar_falha()
        cb.registrar_falha()
        cb.registrar_sucesso()
        assert cb.estado is Estado.FECHADO


class TestAbertura:
    def test_abre_ao_atingir_o_limite(self) -> None:
        cb, _ = breaker()
        for _ in range(3):
            cb.registrar_falha()
        assert cb.estado is Estado.ABERTO
        assert cb.permite() is False

    def test_aberto_da_retry_after(self) -> None:
        cb, relogio = breaker()
        for _ in range(3):
            cb.registrar_falha()
        relogio.agora += 10
        assert cb.retry_after_s() == pytest.approx(20.0)

    def test_aberto_nao_permite_antes_da_espera(self) -> None:
        cb, relogio = breaker()
        for _ in range(3):
            cb.registrar_falha()
        relogio.agora += 29
        assert cb.permite() is False


class TestMeioAberto:
    def test_vira_meio_aberto_apos_a_espera(self) -> None:
        cb, relogio = breaker()
        for _ in range(3):
            cb.registrar_falha()
        relogio.agora += 31
        assert cb.estado is Estado.MEIO_ABERTO
        assert cb.permite() is True

    def test_sucesso_em_meio_aberto_fecha(self) -> None:
        cb, relogio = breaker()
        for _ in range(3):
            cb.registrar_falha()
        relogio.agora += 31
        cb.registrar_sucesso()
        assert cb.estado is Estado.FECHADO

    def test_falha_em_meio_aberto_reabre(self) -> None:
        cb, relogio = breaker()
        for _ in range(3):
            cb.registrar_falha()
        relogio.agora += 31
        _ = cb.estado
        cb.registrar_falha()
        assert cb.estado is Estado.ABERTO


class TestIsolamento:
    def test_circuitos_de_ufs_diferentes_sao_independentes(self) -> None:
        go, _ = breaker(nome="sefaz-52")
        sp, _ = breaker(nome="sefaz-35")
        for _ in range(3):
            go.registrar_falha()
        assert go.estado is Estado.ABERTO
        assert sp.estado is Estado.FECHADO, "queda em GO não pode parar SP"


class TestReset:
    def test_resetar_volta_a_fechado(self) -> None:
        cb, _ = breaker()
        for _ in range(3):
            cb.registrar_falha()
        cb.resetar()
        assert cb.estado is Estado.FECHADO
        assert cb.permite() is True
