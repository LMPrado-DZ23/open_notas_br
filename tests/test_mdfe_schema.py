"""Validador de MDF-e contra o schema oficial versionado 3.00."""

from __future__ import annotations

import pytest
from app.mdfe import ErroMDFe, validar


class TestValidacao:
    def test_xml_malformado_e_recusado(self) -> None:
        with pytest.raises(ErroMDFe, match="malformado"):
            validar(b"<nao-fechado>")

    def test_raiz_de_outro_documento_e_recusada(self) -> None:
        xml = b'<CTe xmlns="http://www.portalfiscal.inf.br/cte" versao="4.00"/>'
        with pytest.raises(ErroMDFe, match="leiaute do MDF-e"):
            validar(xml)

    def test_mdfe_vazio_e_recusado(self) -> None:
        # Bem formado e com a raiz certa, mas sem os grupos obrigatórios.
        xml = b'<MDFe xmlns="http://www.portalfiscal.inf.br/mdfe" versao="3.00"/>'
        with pytest.raises(ErroMDFe, match="leiaute do MDF-e"):
            validar(xml)

    def test_schema_carrega(self) -> None:
        # Prova que o pacote versionado abre como XMLSchema (imports resolvidos).
        from app.mdfe import _validador

        assert _validador() is not None
