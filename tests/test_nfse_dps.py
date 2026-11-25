"""Testes da montagem da DPS e da assinatura XMLDSig.

A verificação de assinatura usa um certificado gerado em tempo de execução. Isso
prova integridade contra aquele certificado — **não** prova aceitação pela SEFIN,
que exige homologação oficial com A1 real.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from xml.etree import ElementTree as ET

import pytest
from app.certificates.cofre import CertificadoA1
from app.db.models.enums import AmbienteFiscal
from app.nfse.constants import FUSO_BR, NS_NFSE
from app.nfse.dps import (
    DpsInput,
    Endereco,
    ErroDps,
    Ibscbs,
    Prestador,
    Tomador,
    Tributacao,
    construir_dps,
    dps_para_bytes,
    extrair_id,
    formatar_decimal,
    id_dps,
)
from app.nfse.signer import (
    ErroAssinatura,
    assinar_bytes,
    assinar_dps,
    assinatura_sem_prefixo,
    verificar,
)
from lxml import etree

from tests.test_fase2_certificado import SENHA, gerar_pfx

CNPJ = "11222333000181"
MUNICIPIO = "3550308"


def entrada(**kwargs) -> DpsInput:
    base = DpsInput(
        ambiente=AmbienteFiscal.HOMOLOGACAO,
        c_mun_emissor=MUNICIPIO,
        serie=1,
        n_dps=42,
        dh_emi=datetime(2026, 11, 25, 12, 0, 0, tzinfo=FUSO_BR),
        prestador=Prestador(documento=CNPJ, op_simp_nac="1", inscricao_municipal="123456"),
        c_trib_nac="010701",
        x_desc_serv="Corte de cabelo masculino",
        valor=Decimal("85.00"),
        tributacao=Tributacao(trib_issqn="1", tp_ret_issqn="1", p_aliq=Decimal("0.05")),
    )
    for chave, valor in kwargs.items():
        setattr(base, chave, valor)
    return base


class TestIdDps:
    def test_layout_de_45_posicoes(self) -> None:
        identificador = id_dps(MUNICIPIO, CNPJ, 1, 42)
        assert len(identificador) == 45
        assert identificador.startswith("DPS")
        assert identificador[3:10] == MUNICIPIO
        assert identificador[10] == "2", "tpInsc 2 = CNPJ"
        assert identificador[-20:-15] == "00001"  # série
        assert identificador[-15:] == "000000000000042"  # número

    def test_cpf_usa_tpinsc_1(self) -> None:
        identificador = id_dps(MUNICIPIO, "11144477735", 1, 1)
        assert identificador[10] == "1"

    def test_documento_ausente_falha(self) -> None:
        with pytest.raises(ErroDps, match="documento do prestador"):
            id_dps(MUNICIPIO, "", 1, 1)


class TestValidacao:
    def test_serie_fora_da_faixa_para_api(self) -> None:
        with pytest.raises(ErroDps, match="série"):
            construir_dps(entrada(serie=70000))

    def test_numero_zero(self) -> None:
        with pytest.raises(ErroDps, match="número da DPS"):
            construir_dps(entrada(n_dps=0))

    def test_valor_zero(self) -> None:
        with pytest.raises(ErroDps, match="valor do serviço"):
            construir_dps(entrada(valor=Decimal("0")))

    def test_descricao_vazia(self) -> None:
        with pytest.raises(ErroDps, match="descrição"):
            construir_dps(entrada(x_desc_serv="   "))

    def test_municipio_invalido(self) -> None:
        with pytest.raises(ErroDps, match="município emissor"):
            construir_dps(entrada(c_mun_emissor="355030"))

    def test_ctribnac_invalido(self) -> None:
        with pytest.raises(ErroDps, match="cTribNac"):
            construir_dps(entrada(c_trib_nac="0107"))

    def test_data_sem_fuso_e_recusada(self) -> None:
        with pytest.raises(ErroDps, match="fuso"):
            construir_dps(entrada(dh_emi=datetime(2026, 11, 25, 12, 0, 0)))

    def test_me_epp_exige_regime_do_simples(self) -> None:
        with pytest.raises(ErroDps, match="regApTribSN"):
            construir_dps(entrada(prestador=Prestador(documento=CNPJ, op_simp_nac="3")))

    def test_ibscbs_exige_nbs(self) -> None:
        with pytest.raises(ErroDps, match="NBS"):
            construir_dps(
                entrada(ibscbs=Ibscbs(c_ind_op="000001", c_class_trib="000001", c_nbs=""))
            )


class TestEstrutura:
    def test_ordem_dos_elementos_no_infdps_nt009(self) -> None:
        # Homologação já opera na NT 009, então `finNFSe` entra depois de tpEmit.
        raiz = construir_dps(entrada())
        inf = raiz.find(f"{{{NS_NFSE}}}infDPS")
        assert inf is not None
        ordem = [etree_tag(e) for e in inf]
        assert ordem[:9] == [
            "tpAmb",
            "dhEmi",
            "verAplic",
            "serie",
            "nDPS",
            "dCompet",
            "tpEmit",
            "finNFSe",
            "cLocEmi",
        ], ordem

    def test_ordem_sem_finnfse_no_leiaute_anterior(self) -> None:
        # Produção antes de 01/12/2026 ainda não tem `finNFSe` em infDPS.
        entrada_antiga = entrada(
            ambiente=AmbienteFiscal.PRODUCAO,
            dh_emi=datetime(2026, 11, 20, 10, 0, 0, tzinfo=FUSO_BR),
        )
        raiz = construir_dps(entrada_antiga)
        inf = raiz.find(f"{{{NS_NFSE}}}infDPS")
        assert inf is not None
        ordem = [etree_tag(e) for e in inf]
        assert "finNFSe" not in ordem
        assert ordem[6:8] == ["tpEmit", "cLocEmi"]

    def test_id_no_infdps(self) -> None:
        raiz = construir_dps(entrada())
        inf = raiz.find(f"{{{NS_NFSE}}}infDPS")
        assert inf is not None
        assert inf.get("Id") == id_dps(MUNICIPIO, CNPJ, 1, 42)

    def test_prestador_com_regime(self) -> None:
        xml = dps_para_bytes(entrada())
        assert b"<CNPJ>11222333000181</CNPJ>" in xml
        assert b"<opSimpNac>1</opSimpNac>" in xml
        assert b"<regEspTrib>0</regEspTrib>" in xml

    def test_valor_formatado_com_duas_casas(self) -> None:
        xml = dps_para_bytes(entrada(valor=Decimal("85.5")))
        assert b"<vServ>85.50</vServ>" in xml

    def test_tomador_com_endereco(self) -> None:
        tomador = Tomador(
            nome="Cliente Exemplo",
            documento="11144477735",
            endereco=Endereco(
                logradouro="Rua A",
                numero="100",
                bairro="Centro",
                codigo_municipio=MUNICIPIO,
                uf="SP",
                cep="01001000",
            ),
        )
        xml = dps_para_bytes(entrada(tomador=tomador))
        assert b"<CPF>11144477735</CPF>" in xml
        assert b"<cMun>3550308</cMun>" in xml
        assert b"<CEP>01001000</CEP>" in xml

    def test_sem_ibscbs_nao_emite_grupo(self) -> None:
        xml = dps_para_bytes(entrada())
        assert b"IBSCBS" not in xml

    def test_ibscbs_declara_classificacao_sem_aliquota(self) -> None:
        ibs = Ibscbs(c_ind_op="000001", c_class_trib="000001", c_nbs="123456789")
        xml = dps_para_bytes(entrada(ibscbs=ibs))

        assert b"<cIndOp>000001</cIndOp>" in xml
        assert b"<CST>000</CST>" in xml
        assert b"<cClassTrib>000001</cClassTrib>" in xml
        # A DPS não carrega alíquota nem valor de IBS/CBS: a SEFIN calcula e
        # devolve em infNFSe/IBSCBS. `pAliq` do XML é o ISS, que é outro tributo.
        for tag_proibida in (b"pIBSUF", b"pIBSMun", b"pCBS", b"vIBS", b"vCBS", b"vTotIBSCBS"):
            assert tag_proibida not in xml, tag_proibida

    def test_nt009_move_finnfse_e_inverte_cnbs(self) -> None:
        ibs = Ibscbs(c_ind_op="000001", c_class_trib="000001", c_nbs="123456789")
        # Data depois da virada: produção em NT 009.
        entrada_nt = entrada(
            ambiente=AmbienteFiscal.PRODUCAO,
            dh_emi=datetime(2026, 12, 15, 10, 0, 0, tzinfo=FUSO_BR),
            ibscbs=ibs,
        )
        xml = dps_para_bytes(entrada_nt)
        assert b"<finNFSe>0</finNFSe>" in xml
        # Ordem: cNBS antes de xDescServ no cServ.
        pos_cnbs = xml.index(b"<cNBS>")
        pos_desc = xml.index(b"<xDescServ>")
        assert pos_cnbs < pos_desc

    def test_leiaute_anterior_mantem_ordem_antiga(self) -> None:
        ibs = Ibscbs(c_ind_op="000001", c_class_trib="000001", c_nbs="123456789")
        entrada_antiga = entrada(
            ambiente=AmbienteFiscal.PRODUCAO,
            dh_emi=datetime(2026, 11, 20, 10, 0, 0, tzinfo=FUSO_BR),
            ibscbs=ibs,
        )
        xml = dps_para_bytes(entrada_antiga)
        assert xml.index(b"<xDescServ>") < xml.index(b"<cNBS>")

    def test_extrair_id_do_xml(self) -> None:
        xml = dps_para_bytes(entrada())
        assert extrair_id(xml) == id_dps(MUNICIPIO, CNPJ, 1, 42)

    def test_extrair_id_de_xml_invalido(self) -> None:
        assert extrair_id(b"nao e xml") is None


def etree_tag(elemento: ET.Element) -> str:
    tag = elemento.tag
    return tag.rsplit("}", 1)[1] if "}" in tag else tag


class TestFormatacao:
    @pytest.mark.parametrize(
        ("valor", "esperado"),
        [
            (Decimal("85"), "85.00"),
            (Decimal("85.5"), "85.50"),
            (Decimal("85.555"), "85.56"),
            (Decimal("0.005"), "0.01"),
        ],
    )
    def test_decimal(self, valor: Decimal, esperado: str) -> None:
        assert formatar_decimal(valor) == esperado

    def test_none(self) -> None:
        assert formatar_decimal(None) is None


# ---------------------------------------------------------------------------
# Assinatura
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def certificado() -> CertificadoA1:
    return CertificadoA1.de_pfx(gerar_pfx(), SENHA)


class TestAssinatura:
    def test_assinatura_verifica(self, certificado: CertificadoA1) -> None:
        dps = dps_para_bytes(entrada())
        assinada = assinar_dps(dps, certificado)

        assert verificar(assinada, certificado) is True

    def test_assinatura_fica_sem_prefixo(self, certificado: CertificadoA1) -> None:
        # A SEFIN rejeita prefixo de namespace na Signature (E1228).
        assinada = assinar_dps(dps_para_bytes(entrada()), certificado)
        assert assinatura_sem_prefixo(assinada) is True

    def test_referencia_aponta_para_o_id_da_dps(self, certificado: CertificadoA1) -> None:
        assinada = assinar_dps(dps_para_bytes(entrada()), certificado)
        raiz = etree.fromstring(assinada)
        referencia = raiz.find(".//{http://www.w3.org/2000/09/xmldsig#}Reference")
        assert referencia is not None
        esperado = "#" + id_dps(MUNICIPIO, CNPJ, 1, 42)
        assert referencia.get("URI") == esperado

    def test_algoritmos_sao_sha256(self, certificado: CertificadoA1) -> None:
        assinada = assinar_dps(dps_para_bytes(entrada()), certificado)
        texto = assinada.decode()
        assert "rsa-sha256" in texto
        assert "xml-exc-c14n" in texto

    def test_conteudo_alterado_invalida_assinatura(self, certificado: CertificadoA1) -> None:
        assinada = assinar_dps(dps_para_bytes(entrada()), certificado)
        adulterada = assinada.replace(b"85.00", b"99.00")
        assert verificar(adulterada, certificado) is False

    def test_outro_certificado_nao_verifica(self, certificado: CertificadoA1) -> None:
        outro = CertificadoA1.de_pfx(gerar_pfx(), SENHA)
        assinada = assinar_dps(dps_para_bytes(entrada()), certificado)
        assert verificar(assinada, outro) is False

    def test_verificar_sem_certificado_e_erro(self) -> None:
        with pytest.raises(ErroAssinatura):
            verificar(b"<DPS/>")

    def test_xml_malformado_para_assinar(self, certificado: CertificadoA1) -> None:
        with pytest.raises(ErroAssinatura, match="mal formado"):
            assinar_bytes(b"<DPS><infDPS>", certificado)

    def test_sem_elemento_com_id(self, certificado: CertificadoA1) -> None:
        with pytest.raises(ErroAssinatura, match="Id"):
            assinar_bytes(b"<DPS><infDPS/></DPS>", certificado)
