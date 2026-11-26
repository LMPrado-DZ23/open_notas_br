"""Validador de CT-e: usa o schema oficial versionado."""

from __future__ import annotations

import pytest
from app.cte import ErroCTe, validar


class TestValidacao:
    def test_xml_malformado_e_recusado(self) -> None:
        with pytest.raises(ErroCTe, match="malformado"):
            validar(b"<nao-fechado>")

    def test_raiz_errada_e_recusada_pelo_schema(self) -> None:
        # Bem formado, mas não é CT-e: o schema precisa recusar.
        with pytest.raises(ErroCTe, match="leiaute do CT-e"):
            validar(b'<NFe xmlns="http://www.portalfiscal.inf.br/nfe"/>')

    def test_cte_sem_campos_obrigatorios_e_recusado(self) -> None:
        # Esta é a razão de existir do validador: um gerador que esqueça `ide` ou `emit`
        # produz XML bem formado e inválido. Sem validar, o erro apareceria no autorizador.
        xml = b'<CTe xmlns="http://www.portalfiscal.inf.br/cte" versao="4.00"/>'
        with pytest.raises(ErroCTe, match="leiaute do CT-e"):
            validar(xml)

    def test_schema_carrega(self) -> None:
        # Prova que o arquivo versionado abre como XMLSchema: se o pacote estivesse
        # corrompido ou faltando um import, a falha apareceria aqui, não em produção.
        from app.cte import _validador

        assert _validador() is not None
