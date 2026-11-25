"""Fixtures compartilhadas dos testes do notasbr."""

from __future__ import annotations

import pytest

from tests.construir import cte, nfe


@pytest.fixture
def xml_nfe() -> bytes:
    """NF-e 4.00 sintética e autoconsistente (só o aviso ASSIN-005 é esperado)."""
    return nfe()


@pytest.fixture
def xml_cte() -> bytes:
    """CT-e 4.00 sintético e autoconsistente."""
    return cte()
