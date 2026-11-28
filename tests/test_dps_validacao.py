"""Validação da DPS: cada regra recusa com mensagem própria, antes de tocar a rede.

O gerador recusa **antes** de emitir: documento ausente, série/nDPS inválidos, `dhEmi` sem fuso,
descrição vazia ou longa demais, códigos fora do formato, Simples sem `regApTribSN`, tomador sem nome,
endereço incoerente, IBS/CBS incompleto. Cada uma dessas validações existe porque a SEFIN devolveria
rejeição genérica — e o cliente perderia a tentativa sem saber o que corrigir.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from app.db.models.enums import AmbienteFiscal
from app.nfse.constants import FUSO_BR
from app.nfse.dps import (
    DpsInput,
    Endereco,
    ErroDps,
    Ibscbs,
    Prestador,
    Tomador,
    Tributacao,
    dps_para_bytes,
    id_dps,
)

ENDERECO = Endereco(
    logradouro="Rua A",
    numero="1",
    bairro="Centro",
    codigo_municipio="5200258",
    uf="GO",
    cep="72900000",
)


def _entrada(**overrides) -> DpsInput:
    base = dict(
        ambiente=AmbienteFiscal.HOMOLOGACAO,
        c_mun_emissor="5200258",
        serie=1,
        n_dps=1,
        dh_emi=datetime(2026, 11, 28, 9, 0, tzinfo=FUSO_BR),
        prestador=Prestador(documento="64339333000122"),
        tomador=Tomador(nome="Tomador LTDA", documento="11222333000181", endereco=ENDERECO),
        c_trib_nac="010701",
        x_desc_serv="Servico de teste",
        valor=Decimal("10.00"),
    )
    base.update(overrides)
    return DpsInput(**base)


def _recusa(entrada: DpsInput, trecho: str) -> None:
    with pytest.raises(ErroDps) as erro:
        dps_para_bytes(entrada)
    assert trecho in str(erro.value), f"mensagem inesperada: {erro.value}"


class TestIdDps:
    def test_documento_vazio_recusa(self) -> None:
        with pytest.raises(ErroDps) as erro:
            id_dps("5200258", "", 1, 1)

        assert "documento do prestador ausente" in str(erro.value)

    def test_id_tem_45_posicoes_e_prefixo(self) -> None:
        valor = id_dps("5200258", "64339333000122", 1, 9)

        assert len(valor) == 45 and valor.startswith("DPS5200258")


class TestValidacaoDaEntrada:
    def test_municipio_emissor_fora_de_7_digitos(self) -> None:
        """Eu supus que o gerador não validava `cLocEmi`; ele valida. A mensagem é explícita."""
        _recusa(_entrada(c_mun_emissor="520"), "município emissor")

    def test_serie_negativa(self) -> None:
        _recusa(_entrada(serie=-1), "série")

    def test_n_dps_zero(self) -> None:
        _recusa(_entrada(n_dps=0), "número da DPS")

    def test_dh_emi_sem_fuso(self) -> None:
        _recusa(_entrada(dh_emi=datetime(2026, 11, 28, 9, 0)), "fuso")

    def test_valor_zero(self) -> None:
        _recusa(_entrada(valor=Decimal("0")), "valor do serviço")

    def test_descricao_vazia(self) -> None:
        _recusa(_entrada(x_desc_serv="   "), "descrição do serviço é obrigatória")

    def test_descricao_longa_demais(self) -> None:
        _recusa(_entrada(x_desc_serv="x" * 2001), "2000")

    @pytest.mark.parametrize("codigo", ["12345", "abcdef", ""])
    def test_c_trib_nac_invalido(self, codigo: str) -> None:
        _recusa(_entrada(c_trib_nac=codigo), "cTribNac")

    def test_c_trib_mun_nao_numerico_recusa(self) -> None:
        _recusa(_entrada(c_trib_mun="ab"), "cTribMun")

    def test_op_simp_nac_invalido(self) -> None:
        _recusa(
            _entrada(prestador=Prestador(documento="64339333000122", op_simp_nac="9")), "opSimpNac"
        )

    def test_reg_esp_trib_invalido(self) -> None:
        _recusa(
            _entrada(prestador=Prestador(documento="64339333000122", reg_esp_trib="9")),
            "regEspTrib",
        )

    def test_simples_sem_regime_especial_recusa(self) -> None:
        _recusa(
            _entrada(
                prestador=Prestador(
                    documento="64339333000122", op_simp_nac="3", reg_ap_trib_sn=None
                )
            ),
            "regApTribSN",
        )

    def test_trib_issqn_invalido(self) -> None:
        _recusa(_entrada(tributacao=Tributacao(trib_issqn="9")), "tribISSQN")

    def test_tp_ret_issqn_invalido(self) -> None:
        _recusa(_entrada(tributacao=Tributacao(tp_ret_issqn="9")), "tpRetISSQN")

    def test_tomador_sem_nome_recusa(self) -> None:
        _recusa(_entrada(tomador=Tomador(nome="   ")), "nome do tomador")

    def test_documento_do_tomador_invalido(self) -> None:
        _recusa(_entrada(tomador=Tomador(nome="X", documento="123")), "documento do tomador")

    def test_documento_do_prestador_invalido(self) -> None:
        _recusa(_entrada(prestador=Prestador(documento="123")), "documento do prestador")


class TestEndereco:
    def test_codigo_de_municipio_invalido(self) -> None:
        ruim = Endereco("Rua A", "1", "Centro", "52", "GO", "72900000")
        _recusa(_entrada(tomador=Tomador(nome="X", endereco=ruim)), "município do tomador")

    def test_uf_invalida(self) -> None:
        ruim = Endereco("Rua A", "1", "Centro", "5200258", "GOI", "72900000")
        _recusa(_entrada(tomador=Tomador(nome="X", endereco=ruim)), "UF do tomador")

    def test_cep_invalido(self) -> None:
        ruim = Endereco("Rua A", "1", "Centro", "5200258", "GO", "729")
        _recusa(_entrada(tomador=Tomador(nome="X", endereco=ruim)), "CEP do tomador")


class TestIbscbs:
    @pytest.mark.parametrize(
        ("campo", "valor", "trecho"),
        [
            ("c_ind_op", "123", "cIndOp"),
            ("c_class_trib", "12", "cClassTrib"),
            ("c_nbs", "", "NBS"),
            ("ind_dest", "7", "indDest"),
        ],
    )
    def test_campos_invalidos(self, campo: str, valor: str, trecho: str) -> None:
        dados = {"c_ind_op": "100301", "c_class_trib": "000001", "c_nbs": "123456789"}
        dados[campo] = valor

        _recusa(_entrada(ibscbs=Ibscbs(**dados)), trecho)

    def test_inddest_padrao_zero_sem_destinatario(self) -> None:
        bruto = dps_para_bytes(
            _entrada(
                ibscbs=Ibscbs(
                    c_ind_op="100301", c_class_trib="000001", c_nbs="123456789", ind_dest="0"
                )
            )
        ).decode()

        assert "<indDest>0</indDest>" in bruto

    def test_destinatario_informado_usa_inddest_um(self) -> None:
        bruto = dps_para_bytes(
            _entrada(
                ibscbs=Ibscbs(
                    c_ind_op="100301",
                    c_class_trib="000001",
                    c_nbs="123456789",
                    ind_dest="1",
                    destinatario=Tomador(nome="Destino", documento="11222333000181"),
                )
            )
        ).decode()

        assert "<indDest>1</indDest>" in bruto
        assert "<dest>" in bruto


class TestRamosRestantes:
    def test_valor_nao_numerico_recusa(self) -> None:
        """Passar string no lugar de Decimal é erro de programação, e a mensagem diz qual."""
        from app.nfse.dps import _decimal

        with pytest.raises(ErroDps) as erro:
            _decimal("abc")

        assert "valor numérico inválido" in str(erro.value)

    def test_tomador_com_cpf_usa_elemento_cpf(self) -> None:
        bruto = dps_para_bytes(
            _entrada(tomador=Tomador(nome="Pessoa", documento="11144477735"))
        ).decode()

        assert "<CPF>11144477735</CPF>" in bruto

    def test_prestador_pode_ser_cpf(self) -> None:
        bruto = dps_para_bytes(_entrada(prestador=Prestador(documento="11144477735"))).decode()

        assert "<CPF>11144477735</CPF>" in bruto

    def test_me_epp_emite_regime_especial(self) -> None:
        bruto = dps_para_bytes(
            _entrada(
                prestador=Prestador(documento="64339333000122", op_simp_nac="3", reg_ap_trib_sn="1")
            )
        ).decode()

        assert "<regApTribSN>1</regApTribSN>" in bruto

    def test_aliquota_informada_vira_paliq(self) -> None:
        bruto = dps_para_bytes(_entrada(tributacao=Tributacao(p_aliq=Decimal("0.05")))).decode()

        assert "<pAliq>0.05</pAliq>" in bruto

    def test_me_epp_com_percentual_usa_ptotribsn(self) -> None:
        bruto = dps_para_bytes(
            _entrada(
                prestador=Prestador(
                    documento="64339333000122", op_simp_nac="3", reg_ap_trib_sn="1"
                ),
                tributacao=Tributacao(p_tot_trib_sn=Decimal("5.00")),
            )
        ).decode()

        assert "<pTotTribSN>5.00</pTotTribSN>" in bruto

    def test_mei_sem_percentual_usa_indtottrib(self) -> None:
        """MEI não pode informar `pTotTribSN`; o leiaute pede `indTotTrib`."""
        bruto = dps_para_bytes(
            _entrada(prestador=Prestador(documento="64339333000122", op_simp_nac="2"))
        ).decode()

        assert "<indTotTrib>0</indTotTrib>" in bruto

    def test_leiaute_anterior_mantem_finnfse_no_grupo_ibscbs(self) -> None:
        """Antes de 01/12/2026 a produção ainda usa o leiaute anterior."""
        bruto = dps_para_bytes(
            _entrada(
                ambiente=AmbienteFiscal.PRODUCAO,
                dh_emi=datetime(2026, 11, 20, 9, 0, tzinfo=FUSO_BR),
                ibscbs=Ibscbs(c_ind_op="100301", c_class_trib="000001", c_nbs="123456789"),
            )
        ).decode()

        assert "<indDest>" not in bruto
        grupo = bruto.split("<IBSCBS>")[1]
        assert "<finNFSe>0</finNFSe>" in grupo

    def test_descontos_incondicional_e_condicional(self) -> None:
        bruto = dps_para_bytes(
            _entrada(v_desc_incond=Decimal("1.00"), v_desc_cond=Decimal("2.00"))
        ).decode()

        assert "<vDescIncond>1.00</vDescIncond>" in bruto
        assert "<vDescCond>2.00</vDescCond>" in bruto


class TestExtrairId:
    def test_le_id_do_infdps(self) -> None:
        from app.nfse.dps import extrair_id

        bruto = dps_para_bytes(_entrada())

        assert extrair_id(bruto).startswith("DPS5200258")

    def test_xml_invalido_devolve_none(self) -> None:
        from app.nfse.dps import extrair_id

        assert extrair_id(b"<nao-fechado>") is None

    def test_sem_infdps_devolve_none(self) -> None:
        from app.nfse.dps import extrair_id

        assert extrair_id(b"<raiz><outro/></raiz>") is None
