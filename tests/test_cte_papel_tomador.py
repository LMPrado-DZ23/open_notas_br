"""Papel do tomador: o leiaute decide, não o gerador."""

from __future__ import annotations

import pytest
from app.cte import PapelTomador


class TestPapelTomador:
    def test_codigos_do_leiaute(self) -> None:
        # Valores do leiaute, não escolha nossa: 0 remetente, 1 expedidor, 2 recebedor,
        # 3 destinatário, 4 outros.
        assert [p.value for p in PapelTomador] == ["0", "1", "2", "3", "4"]

    def test_partes_conhecidas_usam_toma3(self) -> None:
        for papel in (
            PapelTomador.REMETENTE,
            PapelTomador.EXPEDIDOR,
            PapelTomador.RECEBEDOR,
            PapelTomador.DESTINATARIO,
        ):
            assert papel.grupo == "toma3"
            assert papel.exige_dados_proprios is False

    def test_outros_exige_toma4_e_dados_proprios(self) -> None:
        # `toma4` obriga documento e endereço: o tomador não é parte do documento.
        assert PapelTomador.OUTROS.grupo == "toma4"
        assert PapelTomador.OUTROS.exige_dados_proprios is True

    def test_nao_existe_default(self) -> None:
        # Consequência de desenho: não há valor padrão. Quem chama precisa decidir, e é por
        # isso que o gerador não pode assumir `toma3` em silêncio.
        with pytest.raises(TypeError):
            PapelTomador()  # type: ignore[call-arg]
