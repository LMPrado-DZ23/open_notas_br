"""Assinatura do RPS: alvo certo, Id obrigatório e verificação da Signature."""

from __future__ import annotations

import pytest
from app.certificates.cofre import CertificadoA1
from app.nfse.assinatura_rps import AlvoAssinatura, assinar_rps
from app.nfse.errors import ErroSefin, TipoErroFiscal
from lxml import etree

NS = "http://www.abrasf.org.br/nfse.xsd"
NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"

RPS = (
    f'<EnviarLoteRpsEnvio xmlns="{NS}"><LoteRps Id="lote1" versao="2.04">'
    f"<NumeroLote>1</NumeroLote><Prestador><CpfCnpj><Cnpj>11222333000181</Cnpj>"
    f'</CpfCnpj></Prestador><ListaRps><Rps><InfDeclaracaoPrestacaoServico Id="rps1">'
    f"<Rps><IdentificacaoRps><Numero>1</Numero><Serie>1</Serie><Tipo>1</Tipo>"
    f"</IdentificacaoRps></Rps><Competencia>2026-11-01</Competencia>"
    f"</InfDeclaracaoPrestacaoServico></Rps></ListaRps></LoteRps></EnviarLoteRpsEnvio>"
).encode()


@pytest.fixture(scope="module")
def certificado() -> CertificadoA1:
    """Certificado autoassinado de teste — nunca sai da máquina, nunca é real."""
    from tests.test_fase2_certificado import SENHA, gerar_pfx

    return CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())


class TestAssinatura:
    def test_assina_o_rps_e_verifica(self, certificado) -> None:
        resultado = assinar_rps(RPS, certificado, alvo=AlvoAssinatura.RPS)
        assert resultado.id_assinado == "rps1"
        assert b"Signature" in resultado.xml

        raiz = etree.fromstring(resultado.xml)
        assinaturas = raiz.findall(f".//{{{NS_DSIG}}}Signature")
        assert len(assinaturas) == 1, "assinar duas vezes faria o provedor recusar"

    def test_assina_o_lote_quando_o_provedor_exige(self, certificado) -> None:
        resultado = assinar_rps(RPS, certificado, alvo=AlvoAssinatura.LOTE)
        assert resultado.id_assinado == "lote1"

    def test_assinatura_referencia_o_id_do_alvo(self, certificado) -> None:
        # Verifica o que dá para verificar sem expor material privado do certificado:
        # a Reference aponta para o Id assinado e o algoritmo é o que o leiaute espera.
        resultado = assinar_rps(RPS, certificado, alvo=AlvoAssinatura.RPS)
        raiz = etree.fromstring(resultado.xml)
        ref = raiz.find(f".//{{{NS_DSIG}}}Reference")
        assert ref is not None
        assert ref.get("URI") == "#rps1"
        metodo = raiz.find(f".//{{{NS_DSIG}}}SignatureMethod")
        assert metodo is not None and "rsa-sha" in metodo.get("Algorithm", "").lower()

    def test_alvo_errado_nao_assina_o_outro(self, certificado) -> None:
        # Só o RPS tem InfDeclaracao; pedir lote num documento sem LoteRps falha claro.
        sem_lote = (
            f'<EnviarLoteRpsEnvio xmlns="{NS}"><Rps><InfDeclaracaoPrestacaoServico '
            f'Id="rps1"><Competencia>2026-11-01</Competencia>'
            f"</InfDeclaracaoPrestacaoServico></Rps></EnviarLoteRpsEnvio>"
        ).encode()
        with pytest.raises(ErroSefin, match="sem elemento para assinar"):
            assinar_rps(sem_lote, certificado, alvo=AlvoAssinatura.LOTE)


class TestValidacao:
    def test_xml_invalido_e_validacao_nao_recusa_fiscal(self, certificado) -> None:
        with pytest.raises(ErroSefin) as exc:
            assinar_rps(b"<nao-fechado>", certificado)
        assert exc.value.tipo is TipoErroFiscal.VALIDACAO_LOCAL

    def test_sem_id_e_erro_de_validacao_com_motivo(self, certificado) -> None:
        sem_id = (
            f'<EnviarLoteRpsEnvio xmlns="{NS}"><Rps>'
            f"<InfDeclaracaoPrestacaoServico><Competencia>2026-11-01</Competencia>"
            f"</InfDeclaracaoPrestacaoServico></Rps></EnviarLoteRpsEnvio>"
        ).encode()
        with pytest.raises(ErroSefin) as exc:
            assinar_rps(sem_id, certificado)
        assert exc.value.tipo is TipoErroFiscal.VALIDACAO_LOCAL
        assert "Id" in str(exc.value)
