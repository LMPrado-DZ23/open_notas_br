"""Verificação de integridade dos XSD no boot (§84).

O módulo `app/core/schemas.py` sempre declarou "hash conferido no boot e aborto se divergir" — e nada
chamava `verificar`. A verificação existia, tinha 13 testes, entrou no gate em §83, e o processo subia
sem olhar.

Aqui se prova o comportamento real, e não o declarado:

1. no boot, a verificação **roda** (e loga quando diverge);
2. manifesto ausente **não derruba** o serviço — é estado válido, com aviso;
3. `XSD_INTEGRIDADE_STRICT=true` faz o boot **falhar** quando diverge;
4. o padrão continua sendo WARN: schema divergente não troca risco de integridade por indisponibilidade.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.config import Settings
from app.main import _verificar_integridade_dos_schemas


def _settings(**over) -> Settings:
    base = {"environment": "test", "nfse_adapter": "mock"}
    base.update(over)
    return Settings(**base)


class TestBoot:
    def test_manifesto_real_nao_levanta(self) -> None:
        """Com o manifesto versionado íntegro, o boot segue."""
        _verificar_integridade_dos_schemas(_settings())

    def test_manifesto_ausente_avisa_e_segue(self, monkeypatch, tmp_path: Path) -> None:
        import app.core.schemas as schemas

        monkeypatch.setattr(schemas, "MANIFESTO_PADRAO", tmp_path / "nao_existe.json")

        _verificar_integridade_dos_schemas(_settings())  # não levanta

    def test_diverge_em_warn_nao_levanta(self, monkeypatch, tmp_path: Path) -> None:
        """Divergência em WARN: registra e segue. É o padrão do projeto."""
        import app.core.schemas as schemas

        manifesto = tmp_path / "m.json"
        manifesto.write_text('{"nao_existe.xsd": "' + "0" * 64 + '"}', encoding="utf-8")
        monkeypatch.setattr(schemas, "MANIFESTO_PADRAO", manifesto)

        _verificar_integridade_dos_schemas(_settings(xsd_integridade_strict=False))  # não levanta

    def test_strict_diverge_falha_o_boot(self, monkeypatch, tmp_path: Path) -> None:
        import app.core.schemas as schemas

        manifesto = tmp_path / "m.json"
        manifesto.write_text('{"nao_existe.xsd": "' + "0" * 64 + '"}', encoding="utf-8")
        monkeypatch.setattr(schemas, "MANIFESTO_PADRAO", manifesto)

        with pytest.raises(schemas.ErroDeIntegridade):
            _verificar_integridade_dos_schemas(_settings(xsd_integridade_strict=True))
