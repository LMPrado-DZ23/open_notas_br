"""Correções da emissão REAL — cada teste nasceu de uma rejeição observada.

Sequência real contra a Produção Restrita (25/11/2026), com A1 ICP-Brasil:
E1229 → E0714 → E0004 → E0312 → E0160 → E0429 → E0617 → **AUTORIZADA**.
"""

from __future__ import annotations

from decimal import Decimal

from app.nfse.servico import _aliquota_em_percentual


class TestAliquotaEmPercentual:
    """E0429: `pAliq` é percentual; mandar fração erra o imposto em 100x."""

    def test_fracao_vira_percentual(self) -> None:
        assert _aliquota_em_percentual(Decimal("0.05")) == Decimal("5.00")

    def test_dois_por_cento(self) -> None:
        assert _aliquota_em_percentual(Decimal("0.02")) == Decimal("2.00")

    def test_quantiza_em_duas_casas(self) -> None:
        assert _aliquota_em_percentual(Decimal("0.0255")) == Decimal("2.55")

    def test_none_passa(self) -> None:
        assert _aliquota_em_percentual(None) is None

    def test_erro_de_unidade_valeria_100x(self) -> None:
        # Se a conversão desaparecer, alguém paga 0,05% em vez de 5%.
        assert _aliquota_em_percentual(Decimal("0.05")) == Decimal("5.00")
        assert _aliquota_em_percentual(Decimal("0.05")) != Decimal("0.05")


class TestConfiguracaoAmbigua:
    """Duas configurações no mesmo ambiente não podem ser escolhidas em silêncio."""

    def test_erro_herda_de_erro_de_emissao(self) -> None:
        from app.nfse.servico import ConfiguracaoFiscalAmbigua, ErroDeEmissao

        assert issubclass(ConfiguracaoFiscalAmbigua, ErroDeEmissao)

    def test_mensagem_instrui_informar_municipio(self) -> None:
        from app.nfse.servico import ConfiguracaoFiscalAmbigua

        erro = ConfiguracaoFiscalAmbigua(
            "este tenant tem configuração fiscal para mais de um município "
            "(3550308, 5200258). Informe `municipio_ibge` na emissão"
        )
        assert "municipio_ibge" in str(erro)
