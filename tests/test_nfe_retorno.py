"""Leitura do retorno: lote processado != nota autorizada."""

from __future__ import annotations

import pytest
from app.nfe.retorno import ErroDeRetorno, Situacao, ler

NS = "http://www.portalfiscal.inf.br/nfe"


def retorno_lote(cstat: str, prot_cstat: str | None = None, chave: str = "35" + "0" * 42) -> bytes:
    prot = ""
    if prot_cstat is not None:
        prot = (
            f"<protNFe versao='4.00'><infProt><chNFe>{chave}</chNFe>"
            f"<cStat>{prot_cstat}</cStat><xMotivo>motivo</xMotivo>"
            f"<nProt>135260000000001</nProt>"
            f"<dhRecbto>2026-11-25T12:00:00-03:00</dhRecbto></infProt></protNFe>"
        )
    return (
        f"<retEnviNFe xmlns='{NS}' versao='4.00'><tpAmb>2</tpAmb><verAplic>GO</verAplic>"
        f"<cStat>{cstat}</cStat><xMotivo>motivo do lote</xMotivo>"
        f"<cUF>52</cUF><dhRecbto>2026-11-25T12:00:00-03:00</dhRecbto>{prot}"
        f"</retEnviNFe>"
    ).encode()


class TestLoteProcessadoNaoEAutorizada:
    def test_lote_104_sem_protocolo_nao_e_autorizada(self) -> None:
        # O erro clássico: ler cStat 104 do LOTE e concluir "autorizada".
        retorno = ler(retorno_lote("104"))
        assert retorno.situacao is Situacao.LOTE_PROCESSADO
        assert retorno.autorizada is False

    def test_lote_104_com_protocolo_100_e_autorizada(self) -> None:
        retorno = ler(retorno_lote("104", prot_cstat="100"))
        assert retorno.situacao is Situacao.AUTORIZADA
        assert retorno.protocolos[0].autorizada is True

    def test_lote_104_com_rejeicao_e_rejeitada(self) -> None:
        retorno = ler(retorno_lote("104", prot_cstat="539"))
        assert retorno.autorizada is False
        assert retorno.situacao is Situacao.REJEITADA


class TestRecibo:
    def test_lote_recebido_devolve_recibo(self) -> None:
        xml = (
            f"<retEnviNFe xmlns='{NS}' versao='4.00'><cStat>103</cStat>"
            f"<xMotivo>Lote recebido</xMotivo><nRecibo>521000000000001</nRecibo>"
            f"</retEnviNFe>"
        ).encode()
        retorno = ler(xml)
        assert retorno.situacao is Situacao.LOTE_RECEBIDO
        assert retorno.recibo == "521000000000001"


class TestProtocolo:
    def test_extrai_os_campos_da_prova(self) -> None:
        retorno = ler(retorno_lote("104", prot_cstat="100"))
        prot = retorno.protocolos[0]
        assert prot.chave.startswith("35")
        assert prot.numero_protocolo == "135260000000001"
        assert prot.data_recebimento.startswith("2026-11-25")
        assert prot.xmotivo == "motivo"

    def test_denegacao_e_situacao_propria(self) -> None:
        # Denegada não é rejeição: a nota existe e foi recusada.
        retorno = ler(retorno_lote("104", prot_cstat="110"))
        assert retorno.situacao is Situacao.DENEGADA


class TestRejeicao:
    def test_cstat_de_rejeicao_no_lote(self) -> None:
        retorno = ler(retorno_lote("215"))
        assert retorno.situacao is Situacao.REJEITADA
        assert retorno.autorizada is False


class TestErros:
    def test_xml_invalido(self) -> None:
        with pytest.raises(ErroDeRetorno, match="inválido"):
            ler(b"<nao-fechado>")

    def test_elemento_que_nao_e_retorno(self) -> None:
        with pytest.raises(ErroDeRetorno, match="não é retorno"):
            ler(b"<NFe xmlns='http://www.portalfiscal.inf.br/nfe'/>")

    def test_preserva_o_xml_original(self) -> None:
        bruto = retorno_lote("104", prot_cstat="100")
        assert ler(bruto).xml == bruto
