"""Testes do motor tributário IBS/CBS.

Casos calculados à mão, com a fórmula confirmada no esquema da calculadora
oficial (`NfseBaseCalculoInput`). O teste não recalcula com o mesmo código: os
valores esperados estão escritos no teste.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.tax.rtc import (
    TABELA_ALIQUOTAS,
    AliquotaReferencia,
    BaseCalculoNfse,
    ErroCalculoTributario,
    aliquotas_do_ano,
    calcular_ibscbs,
)


class TestBase:
    def test_so_valor_do_servico(self) -> None:
        base = BaseCalculoNfse(valor_servico=Decimal("100.00"))
        assert base.base() == Decimal("100.00")

    def test_formula_completa(self) -> None:
        base = BaseCalculoNfse(
            valor_servico=Decimal("100.00"),
            desconto_incondicional=Decimal("10.00"),
            v_calc_ree_rep_res=Decimal("2.00"),
            v_calc_ded_red_ibscbs=Decimal("3.00"),
            iss=Decimal("5.00"),
            pis=Decimal("1.65"),
            cofins=Decimal("7.60"),
        )
        # 100 - 10 - 2 - 3 - 5 - 1.65 - 7.60
        assert base.base() == Decimal("70.75")


class TestCalculo:
    def test_aliquotas_de_2026(self) -> None:
        # Tabela oficial ALIQUOTA_REFERENCIA: CBS 0,90% | IBS UF 0,10% | Mun 0,00%
        referencia = aliquotas_do_ano(2026)
        assert referencia is not None
        assert referencia.cbs == Decimal("0.009")
        assert referencia.ibs_uf == Decimal("0.001")
        assert referencia.ibs_mun == Decimal("0.000")
        assert referencia.ibs == Decimal("0.001")

    def test_aliquotas_de_2027(self) -> None:
        # 2027: CBS 8,40% | IBS UF 0,05% | Mun 0,05%
        referencia = aliquotas_do_ano(2027)
        assert referencia is not None
        assert referencia.cbs == Decimal("0.084")
        assert referencia.ibs_uf == Decimal("0.0005")
        assert referencia.ibs_mun == Decimal("0.0005")
        assert referencia.ibs == Decimal("0.001")

    def test_reparticao_do_ibs_no_resultado(self) -> None:
        resultado = calcular_ibscbs(
            BaseCalculoNfse(valor_servico=Decimal("1000.00")), ano_fato_gerador=2026
        )
        # IBS 0,10% em 2026 e integralmente estadual.
        assert resultado.valor_ibs_uf == Decimal("1.00")
        assert resultado.valor_ibs_mun == Decimal("0.00")
        assert resultado.valor_ibs == Decimal("1.00")

    def test_calculo_padrao_2026(self) -> None:
        resultado = calcular_ibscbs(
            BaseCalculoNfse(valor_servico=Decimal("1000.00")), ano_fato_gerador=2026
        )
        # base 1000 | CBS 9.00 | IBS 1.00
        assert resultado.base_calculo == Decimal("1000.00")
        assert resultado.valor_cbs == Decimal("9.00")
        assert resultado.valor_ibs == Decimal("1.00")
        assert resultado.valor_total == Decimal("10.00")
        assert "ALIQUOTA_REFERENCIA" in resultado.fonte_aliquota

    def test_base_reduzida_por_tributos(self) -> None:
        base = BaseCalculoNfse(
            valor_servico=Decimal("100.00"),
            desconto_incondicional=Decimal("10.00"),
            iss=Decimal("5.00"),
            pis=Decimal("1.65"),
            cofins=Decimal("7.60"),
        )
        resultado = calcular_ibscbs(base, ano_fato_gerador=2026)
        # base 75.75 | CBS 0.68175 -> 0.68 | IBS 0.07575 -> 0.08
        assert resultado.base_calculo == Decimal("75.75")
        assert resultado.valor_cbs == Decimal("0.68")
        assert resultado.valor_ibs == Decimal("0.08")
        assert resultado.valor_total == Decimal("0.76")

    def test_arredondamento_meio_para_cima(self) -> None:
        # base 0.50 * 0.009 = 0.0045 -> 0.00 ; * 0.001 = 0.0005 -> 0.00
        resultado = calcular_ibscbs(
            BaseCalculoNfse(valor_servico=Decimal("0.50")), ano_fato_gerador=2026
        )
        assert resultado.valor_cbs == Decimal("0.00")

        # base 100 * 0.005 = 0.5 -> com alíquota explícita de 0.5%
        explicito = calcular_ibscbs(
            BaseCalculoNfse(valor_servico=Decimal("100.00")),
            ano_fato_gerador=2026,
            aliquota_cbs=Decimal("0.005"),
            aliquota_ibs=Decimal("0.005"),
        )
        assert explicito.valor_cbs == Decimal("0.50")

    def test_aliquota_explicita_tem_precedencia(self) -> None:
        resultado = calcular_ibscbs(
            BaseCalculoNfse(valor_servico=Decimal("1000.00")),
            ano_fato_gerador=2026,
            aliquota_cbs=Decimal("0.01"),
            aliquota_ibs=Decimal("0.02"),
        )
        assert resultado.valor_cbs == Decimal("10.00")
        assert resultado.valor_ibs == Decimal("20.00")
        assert resultado.fonte_aliquota == "parâmetro explícito"

    def test_ano_sem_aliquota_e_erro(self) -> None:
        with pytest.raises(ErroCalculoTributario, match="alíquota de referência"):
            calcular_ibscbs(BaseCalculoNfse(valor_servico=Decimal("100.00")), ano_fato_gerador=2035)

    def test_uma_aliquota_so_e_erro(self) -> None:
        with pytest.raises(ErroCalculoTributario, match="duas alíquotas"):
            calcular_ibscbs(
                BaseCalculoNfse(valor_servico=Decimal("100.00")),
                ano_fato_gerador=2026,
                aliquota_cbs=Decimal("0.01"),
            )

    def test_aliquota_fora_da_faixa(self) -> None:
        with pytest.raises(ErroCalculoTributario, match="fora da faixa"):
            calcular_ibscbs(
                BaseCalculoNfse(valor_servico=Decimal("100.00")),
                ano_fato_gerador=2026,
                aliquota_cbs=Decimal("1.5"),
                aliquota_ibs=Decimal("0.001"),
            )

    def test_valor_zero_e_rejeitado(self) -> None:
        with pytest.raises(ErroCalculoTributario, match="maior que zero"):
            calcular_ibscbs(BaseCalculoNfse(valor_servico=Decimal("0")), ano_fato_gerador=2026)


class TestRegras:
    def test_base_negativa_e_erro_com_codigo(self) -> None:
        base = BaseCalculoNfse(valor_servico=Decimal("100.00"), iss=Decimal("150.00"))
        resultado = calcular_ibscbs(base, ano_fato_gerador=2026)

        assert resultado.valido is False
        assert any("BASE-NEGATIVA" in erro for erro in resultado.erros)
        assert resultado.base_calculo == Decimal("0.00")

    def test_mei_recebe_aviso_e1302(self) -> None:
        resultado = calcular_ibscbs(
            BaseCalculoNfse(valor_servico=Decimal("100.00")),
            ano_fato_gerador=2026,
            mei=True,
        )
        assert resultado.valido is True
        assert any("E1302" in aviso for aviso in resultado.avisos)

    def test_optante_pendente_gera_ressalva(self) -> None:
        resultado = calcular_ibscbs(
            BaseCalculoNfse(valor_servico=Decimal("100.00")),
            ano_fato_gerador=2026,
            optante_pendente=True,
        )
        assert any("ressalva" in aviso for aviso in resultado.avisos)

    def test_tabela_e_versionada_por_ano(self) -> None:
        assert set(TABELA_ALIQUOTAS) == {2026, 2027}
        assert isinstance(TABELA_ALIQUOTAS[2026], AliquotaReferencia)
        assert TABELA_ALIQUOTAS[2026].fonte

    def test_sem_reparticao_quando_aliquota_e_explicita(self) -> None:
        resultado = calcular_ibscbs(
            BaseCalculoNfse(valor_servico=Decimal("1000.00")),
            ano_fato_gerador=2026,
            aliquota_cbs=Decimal("0.01"),
            aliquota_ibs=Decimal("0.02"),
        )
        # Sem tabela, não há como afirmar a repartição: fica None, não zero.
        assert resultado.valor_ibs_uf is None
        assert resultado.valor_ibs_mun is None
