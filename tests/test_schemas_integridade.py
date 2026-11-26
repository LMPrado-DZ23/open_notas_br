"""Integridade dos XSD: manifesto, divergência, modo strict e não-manifestado."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.schemas import (
    MANIFESTO_PADRAO,
    ErroDeIntegridade,
    ModoVerificacao,
    carregar_manifesto,
    gerar_manifesto,
    sha256,
    verificar,
)


@pytest.fixture
def schemas(tmp_path: Path) -> Path:
    base = tmp_path / "schemas"
    base.mkdir()
    (base / "a.xsd").write_text("<xs:schema/>", encoding="utf-8")
    (base / "sub").mkdir()
    (base / "sub" / "b.xsd").write_text("<xs:schema>b</xs:schema>", encoding="utf-8")
    return base


class TestManifesto:
    def test_gera_hash_de_cada_arquivo(self, schemas: Path) -> None:
        manifesto = gerar_manifesto(schemas)
        assert set(manifesto) == {"a.xsd", "sub/b.xsd"}
        assert all(len(h) == 64 for h in manifesto.values())

    def test_hash_estavel(self, schemas: Path) -> None:
        assert sha256(schemas / "a.xsd") == sha256(schemas / "a.xsd")

    def test_manifesto_ausente_nao_e_erro(self, tmp_path: Path) -> None:
        assert carregar_manifesto(tmp_path / "nao_existe.json") == {}

    def test_manifesto_ilegivel_levanta(self, tmp_path: Path) -> None:
        ruim = tmp_path / "m.json"
        ruim.write_text("{nao e json", encoding="utf-8")
        with pytest.raises(ErroDeIntegridade, match="ilegível"):
            carregar_manifesto(ruim)


class TestVerificacao:
    def test_sem_divergencia(self, schemas: Path) -> None:
        manifesto = gerar_manifesto(schemas)
        assert verificar(schemas, manifesto) == []

    def test_hash_divergente(self, schemas: Path) -> None:
        manifesto = gerar_manifesto(schemas)
        (schemas / "a.xsd").write_text("<xs:schema>alterado</xs:schema>", encoding="utf-8")
        divergencias = verificar(schemas, manifesto)
        assert len(divergencias) == 1
        assert divergencias[0].tipo == "hash_divergente"

    def test_arquivo_ausente(self, schemas: Path) -> None:
        manifesto = gerar_manifesto(schemas)
        (schemas / "a.xsd").unlink()
        divergencias = verificar(schemas, manifesto)
        assert divergencias[0].tipo == "ausente"

    def test_arquivo_nao_manifestado(self, schemas: Path) -> None:
        # Schema novo que ninguém registrou é tão suspeito quanto um alterado.
        manifesto = gerar_manifesto(schemas)
        (schemas / "novo.xsd").write_text("<xs:schema/>", encoding="utf-8")
        divergencias = verificar(schemas, manifesto)
        assert [d.tipo for d in divergencias] == ["nao_manifestado"]

    def test_modo_warn_nao_levanta(self, schemas: Path) -> None:
        manifesto = gerar_manifesto(schemas)
        (schemas / "a.xsd").unlink()
        assert verificar(schemas, manifesto, modo=ModoVerificacao.WARN)

    def test_modo_strict_levanta(self, schemas: Path) -> None:
        manifesto = gerar_manifesto(schemas)
        (schemas / "a.xsd").unlink()
        with pytest.raises(ErroDeIntegridade, match="não confere"):
            verificar(schemas, manifesto, modo=ModoVerificacao.STRICT)

    def test_diretorio_inexistente(self, tmp_path: Path) -> None:
        with pytest.raises(ErroDeIntegridade, match="inexistente"):
            verificar(tmp_path / "nada", {})


class TestManifestoReal:
    def test_schemas_do_repositorio_conferem(self) -> None:
        """O manifesto versionado bate com os arquivos em `tests/fixtures/schemas`."""
        manifesto = carregar_manifesto(MANIFESTO_PADRAO)
        assert manifesto, "manifesto deve existir e não estar vazio"
        divergencias = verificar("tests/fixtures/schemas", manifesto)
        assert divergencias == [], [d.caminho for d in divergencias]

    def test_manifesto_cobre_as_duas_familias(self) -> None:
        manifesto = carregar_manifesto(MANIFESTO_PADRAO)
        familias = {caminho.split("/")[0] for caminho in manifesto}
        assert "nfe-4.00" in familias
        assert "nfse-1.01" in familias
