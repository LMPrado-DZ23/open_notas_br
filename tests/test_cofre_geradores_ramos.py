"""Ramos de comportamento do cofre de certificado e dos geradores de XML.

Objetivo desta suíte: cobrir os ramos que a suíte existente não exercita **sem** tocar
código de produção. Cada teste aqui afirma um valor gerado, uma exceção com motivo ou um
campo do XML — nada de "não explodiu".

Notas de ambiente, porque importam para quem ler depois:

- nenhum certificado real entra aqui: todo PFX é gerado no teste por
  :func:`tests.test_fase2_certificado.gerar_pfx` (senha ``SENHA``);
- `ssl.enum_certificates` só existe no Windows. Os testes desse ramo usam dublê
  (`monkeypatch`) para simular tanto a loja do SO quanto a ausência dela — o objetivo é o
  comportamento da FUNÇÃO, não a loja da máquina que roda a suíte;
- `com_cep=True` em `app/cte/gerador.py::_endereco` não é alcançável pela API pública
  (`gerar()` sempre passa ``com_cep=False``); o teste chama a função direto e diz isso;
- nenhuma chamada de rede: transportes falsos (`httpx.MockTransport`, classes locais).
"""

from __future__ import annotations

import hashlib
import ssl
import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from app.certificates.cofre import (
    CertificadoA1,
    ErroCertificado,
    _carregar_raizes_do_sistema,
    abrir_pfx,
)
from app.core.crypto import Cofre, aad_do_tenant
from app.cte import ErroCTe, PapelTomador, validar_ou_levantar
from app.cte.consulta import NS_SERVICO as NS_SERVICO_CTE
from app.cte.consulta import consultar_status as consultar_status_cte
from app.cte.consulta_situacao import consultar_situacao
from app.cte.gerador import Parte, _endereco, gerar, gerar_assinado
from app.danfse.model import DanfseData, TributacaoIssqn
from app.danfse.parser import extrair_chave, parse_danfse
from app.danfse.render import _formatar_chave, _quebrar, gerar_danfse
from app.db.models.credencial_municipal import CredencialMunicipalTenant
from app.db.models.enums import AmbienteFiscal
from app.mdfe import ErroMDFe
from app.mdfe import validar as validar_mdfe
from app.mdfe.consulta import NS_SERVICO as NS_SERVICO_MDFE
from app.mdfe.consulta import consultar_status as consultar_status_mdfe
from app.mdfe.gerador import Descarga
from app.mdfe.gerador import gerar as gerar_mdfe
from app.nfe.autorizacao import (
    ErroDeAutorizacao,
    ResultadoAutorizacao,
    consultar_recibo,
)
from app.nfe.base import ErroDeNFe
from app.nfe.gerador import gerar_nfe
from app.nfe.lote import montar_enviNFe
from app.nfe.retorno import CSTAT_AUTORIZADA, Protocolo, Retorno, Situacao, ler
from app.nfe.soap import NS_SOAP12, ErroSOAP, desenvelopar, extrair_falha
from app.nfe.transporte import ClienteSefaz, RespostaSefaz, TransporteHTTP
from app.nfse.constants import LEIAUTE_ANTERIOR, LEIAUTE_NT009, leiaute
from app.nfse.credenciais import segredo
from app.nfse.drivers_factory import MunicipioParaDriver, criar_driver
from app.nfse.errors import ErroSefin, TipoErroFiscal
from app.nfse.evento import ErroDeEvento, PedidoCancelamento, id_evento_registrado
from app.nfse.roteamento import decidir_rota
from app.nfse.schemas import EmissaoIn
from app.nfse.transport import criar_cliente, executar
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, pkcs12
from cryptography.x509.oid import NameOID
from lxml import etree
from pypdf import PdfReader

from tests.test_cte_gerador import dados as dados_cte
from tests.test_fase2_certificado import SENHA, gerar_pfx
from tests.test_mdfe_gerador import dados as dados_mdfe
from tests.test_nfe_gerador import destinatario, emitente, nota

CNPJ = "11222333000181"
NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_CTE = "http://www.portalfiscal.inf.br/cte"
NS_MDFE = "http://www.portalfiscal.inf.br/mdfe"


# ---------------------------------------------------------------------------
# cofre do certificado
# ---------------------------------------------------------------------------
def _ca_de_teste_der() -> bytes:
    """Certificado autoassinado com ``CA:TRUE`` em DER, só para o dublê da loja do SO.

    Não é certificado de terceiro nem certificado real: é gerado aqui, com chave
    descartável, e existe para provar que a raiz válida é carregada no contexto.
    """
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CA de teste local")])
    agora = datetime.now(UTC)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora)
        .not_valid_after(agora.replace(year=agora.year + 1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(chave, hashes.SHA256())
    )
    return certificado.public_bytes(Encoding.DER)


class TestRaizesDoSistema:
    """`_carregar_raizes_do_sistema` com a loja do Windows dublada.

    Em Linux a função é inerte (`hasattr` falso). Em Windows ela lê a loja. Nenhum dos
    dois casos pode ser observado de forma estável numa suíte que roda nas duas
    plataformas, então o teste fixa a entrada: a "loja" é uma lista montada à mão.
    """

    def test_plataforma_sem_loja_do_so_devolve_zero(self, monkeypatch) -> None:
        # O contexto é criado ANTES do dublê: no Windows o próprio
        # `create_default_context()` usa `ssl.enum_certificates`.
        contexto = ssl.create_default_context()
        # Simula Linux: sem `ssl.enum_certificates`, a função não pode falhar nem carregar.
        monkeypatch.delattr(ssl, "enum_certificates", raising=False)

        assert _carregar_raizes_do_sistema(contexto) == 0

    def test_loja_indisponivel_devolve_zero(self, monkeypatch) -> None:
        def loja_quebrada(_store: str) -> list[tuple[bytes, str, bool]]:
            raise OSError("repositório de certificados indisponível")

        contexto = ssl.create_default_context()
        monkeypatch.setattr(ssl, "enum_certificates", loja_quebrada)

        assert _carregar_raizes_do_sistema(contexto) == 0

    def test_encoding_que_nao_e_x509_asn_e_ignorado(self, monkeypatch) -> None:
        der = _ca_de_teste_der()
        contexto = ssl.create_default_context()
        monkeypatch.setattr(
            ssl,
            "enum_certificates",
            lambda _store: [(der, "x509_asn", True), (der, "PEM", True)],
        )

        # Só a entrada x509_asn conta; a PEM é pulada pelo `continue`.
        assert _carregar_raizes_do_sistema(contexto) == 1

    def test_raiz_que_o_openssl_recusa_nao_derruba_o_contexto(self, monkeypatch) -> None:
        contexto = ssl.create_default_context()
        monkeypatch.setattr(
            ssl,
            "enum_certificates",
            lambda _store: [(b"isto-nao-e-um-certificado-der", "x509_asn", True)],
        )

        # Comportamento: uma raiz malformada do SO é pulada, e a contagem é zero.
        assert _carregar_raizes_do_sistema(contexto) == 0


class TestAberturaDoPfx:
    def test_senha_bytes_vazia_equivale_a_sem_senha(self) -> None:
        # `b""` precisa virar `None`; senão o OpenSSL tenta abrir PFX sem senha com senha
        # vazia e recusa um arquivo que é válido.
        certificado = CertificadoA1.de_pfx(gerar_pfx(senha=None), b"")
        assert certificado.cnpj == CNPJ

    def test_pkcs12_sem_certificado_recusa_com_motivo(self) -> None:
        chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pfx = pkcs12.serialize_key_and_certificates(
            name=None,
            key=chave,
            cert=None,
            cas=None,
            encryption_algorithm=NoEncryption(),
        )

        with pytest.raises(ErroCertificado, match="par de certificado"):
            CertificadoA1.de_pfx(pfx)

    def test_cnpj_alfanumerico_e_lido_do_common_name(self) -> None:
        # CNPJ alfanumérico (padrão novo): 12 caracteres alfanuméricos + 2 dígitos.
        certificado = CertificadoA1.de_pfx(gerar_pfx(apenas_cn=True, cnpj="AB123456789012"), SENHA)
        assert certificado.cnpj == "AB123456789012"

    def test_sem_cnpj_reconhecivel_devolve_none(self) -> None:
        # Nem SAN, nem CN, nem O trazem 14 caracteres no padrão: o campo é None, não "".
        certificado = CertificadoA1.de_pfx(gerar_pfx(apenas_cn=True, cnpj=None), SENHA)
        assert certificado.cnpj is None

    def test_impressao_arquivo_e_o_sha256_do_certificado_pem(self) -> None:
        # O docstring fala em "SHA-256 do DER", mas a implementação hasheia o PEM
        # (`_cert_pem`). O teste fixa o comportamento observado; a divergência entre
        # docstring e código está no relatório da auditoria.
        certificado = CertificadoA1.de_pfx(gerar_pfx(), SENHA)
        _, certificados = certificado.material_para_assinatura()

        assert (
            certificado.impressao_arquivo()
            == hashlib.sha256(certificados[0].encode("ascii")).hexdigest()
        )
        # Dois certificados distintos não compartilham impressão.
        outro = CertificadoA1.de_pfx(gerar_pfx(), SENHA)
        assert outro.impressao_arquivo() != certificado.impressao_arquivo()


class TestEnvelopeDoPfx:
    def test_envelope_menor_que_o_prefixo_de_tamanho_recusa(self) -> None:
        tenant = uuid.uuid4()
        chave = b"\x21" * 32
        envelope = Cofre(chave).selar(b"\x00\x01\x02", aad=aad_do_tenant(tenant))

        with pytest.raises(ErroCertificado, match="truncado"):
            abrir_pfx(envelope, tenant_id=tenant, chave=chave)


# ---------------------------------------------------------------------------
# NF-e: gerador e peças do ciclo
# ---------------------------------------------------------------------------
class TestCamposOpcionaisDaNFe:
    def test_ie_do_destinatario_sai_quando_informada(self) -> None:
        dest = destinatario()
        dest.ie = "987654321"
        raiz = etree.fromstring(gerar_nfe(nota(destinatario=dest)))

        assert raiz.find(".//{*}dest/{*}indIEDest").text == "1"
        assert raiz.find(".//{*}dest/{*}IE").text == "987654321"

    def test_email_do_destinatario_sai_quando_informado(self) -> None:
        dest = destinatario()
        dest.email = "compras@cliente.test"
        raiz = etree.fromstring(gerar_nfe(nota(destinatario=dest)))

        assert raiz.find(".//{*}dest/{*}email").text == "compras@cliente.test"

    def test_transportadora_sai_com_cnpj_e_nome(self) -> None:
        raiz = etree.fromstring(
            gerar_nfe(
                nota(
                    cnpj_transportadora=CNPJ,
                    nome_transportadora="TRANSPORTES TESTE LTDA",
                )
            )
        )
        transporta = raiz.find(".//{*}transp/{*}transporta")

        assert transporta is not None
        assert transporta.find("{*}CNPJ").text == CNPJ
        assert transporta.find("{*}xNome").text == "TRANSPORTES TESTE LTDA"

    def test_sem_transportadora_nao_cria_o_grupo(self) -> None:
        raiz = etree.fromstring(gerar_nfe(nota()))

        assert raiz.find(".//{*}transp/{*}transporta") is None

    def test_informacoes_adicionais_vao_para_infCpl(self) -> None:
        raiz = etree.fromstring(
            gerar_nfe(nota(informacoes_adicionais="PEDIDO 8842 - ENTREGA PROGRAMADA"))
        )

        assert raiz.find(".//{*}infAdic/{*}infCpl").text == "PEDIDO 8842 - ENTREGA PROGRAMADA"


class TestValidacaoDaNFe:
    def test_destinatario_com_documento_invalido_recusa(self) -> None:
        dest = destinatario()
        dest.documento = "123"
        with pytest.raises(ErroDeNFe, match="CPF"):
            nota(destinatario=dest).validar()

    def test_crt_vazio_recusa(self) -> None:
        emit = emitente()
        emit.crt = ""
        with pytest.raises(ErroDeNFe, match="CRT"):
            nota(emitente=emit).validar()


class TestLoteENFe:
    def test_nfe_que_nao_e_xml_recusa_o_lote(self) -> None:
        with pytest.raises(ErroDeNFe, match="não é XML válido"):
            montar_enviNFe([b"<NFe>"])

    def test_retorno_sem_cstat_nem_protocolo_e_indefinido(self) -> None:
        # Sem informação, a situação é `indefinida` — nunca "autorizada" por omissão.
        retorno = ler(f'<retEnviNFe xmlns="{NS_NFE}" versao="4.00"/>'.encode())

        assert retorno.situacao is Situacao.INDEFINIDA
        assert retorno.autorizada is False


class TestLeituraDoRetorno:
    def test_protocolo_e_none_quando_nenhuma_nota_foi_autorizada(self) -> None:
        protocolo = Protocolo(
            chave="1" * 44,
            cstat="110",
            xmotivo="Denegada",
            numero_protocolo=None,
            data_recebimento=None,
        )
        retorno = Retorno(cstat="104", xmotivo="Lote processado", protocolos=(protocolo,))
        resultado = ResultadoAutorizacao(situacao=retorno.situacao, retorno=retorno)

        assert resultado.situacao is Situacao.DENEGADA
        assert resultado.protocolo is None
        assert resultado.autorizada is False

    def test_retorno_autorizado_tem_protocolo(self) -> None:
        xml = (
            f'<retEnviNFe xmlns="{NS_NFE}"><cStat>104</cStat>'
            f"<protNFe><infProt><chNFe>{'1' * 44}</chNFe>"
            f"<cStat>{CSTAT_AUTORIZADA}</cStat><xMotivo>Autorizado</xMotivo>"
            "</infProt></protNFe></retEnviNFe>"
        ).encode()

        retorno = ler(xml)

        assert retorno.situacao is Situacao.AUTORIZADA
        assert retorno.autorizada is True
        assert retorno.protocolos[0].chave == "1" * 44


_RESPOSTA_FAULT = (
    b'<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
    b"<soap12:Body><soap12:Fault><soap12:Code><soap12:Value>soap:Sender"
    b"</soap12:Value></soap12:Code><soap12:Reason><soap12:Text>schema invalido"
    b"</soap12:Text></soap12:Reason></soap12:Fault></soap12:Body></soap12:Envelope>"
)


class TestConsultarRecibo:
    async def test_fault_na_consulta_vira_erro_de_autorizacao(self) -> None:
        cliente = ClienteSefaz(_TransporteFalso(_RESPOSTA_FAULT))

        with pytest.raises(ErroDeAutorizacao, match="recusou a consulta"):
            await consultar_recibo(
                cliente,
                url="https://homologacao.sefaz.example/nfe/recibo",
                xml_consulta=b"<consReciNFe/>",
            )


class TestEnvelopeSOAP:
    def test_resposta_que_nao_e_xml_recusa(self) -> None:
        with pytest.raises(ErroSOAP, match="não é XML"):
            desenvelopar(b"lixo")

    def test_fault_12_com_filhos_sem_namespace(self) -> None:
        # Alguns autorizadores devolvem `faultcode`/`faultstring` sem namespace, dentro de
        # um Fault SOAP 1.2. O leitor precisa cair no nome alternativo.
        resposta = (
            f'<soap12:Envelope xmlns:soap12="{NS_SOAP12}"><soap12:Body>'
            "<soap12:Fault><faultcode>soap:Client</faultcode>"
            "<faultstring>falha de leiaute</faultstring></soap12:Fault>"
            "</soap12:Body></soap12:Envelope>"
        ).encode()

        assert extrair_falha(resposta) == {"code": "soap:Client", "reason": "falha de leiaute"}


class TestTransporteSoap11:
    async def test_soap_11_usa_text_xml_e_header_soapaction(self) -> None:
        visto: dict[str, str] = {}
        acao = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeStatusServico4/nfeStatusServicoNF"

        async def handler(request: httpx.Request) -> httpx.Response:
            visto["content_type"] = request.headers.get("content-type", "")
            visto["soap_action"] = request.headers.get("soapaction", "")
            return httpx.Response(200, content=b"<retConsStatServ/>")

        cliente_http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        transporte = TransporteHTTP(cliente=cliente_http, soap_action=acao, soap_versao="1.1")
        try:
            await transporte.enviar(
                url="https://homologacao.sefaz.example/nfe/status",
                corpo=b"<x/>",
                timeout_s=5,
            )
        finally:
            await cliente_http.aclose()

        assert visto["content_type"].startswith("text/xml")
        assert visto["soap_action"] == f'"{acao}"'


# ---------------------------------------------------------------------------
# CT-e: validador, consultas e gerador
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def certificado() -> CertificadoA1:
    return CertificadoA1.de_pfx(gerar_pfx(), SENHA)


class TestValidadorDoCTe:
    def test_schema_ausente_recusa_apontando_o_caminho(self, monkeypatch, tmp_path: Path) -> None:
        import app.cte as modulo

        modulo._validador.cache_clear()
        monkeypatch.setattr(modulo, "SCHEMA_PRINCIPAL", tmp_path / "nao-existe.xsd")
        try:
            with pytest.raises(ErroCTe, match="ausente"):
                modulo.validar(b"<CTe/>")
        finally:
            modulo._validador.cache_clear()

    def test_schema_que_nao_compila_recusa_com_motivo(self, monkeypatch, tmp_path: Path) -> None:
        import app.cte as modulo

        quebrado = tmp_path / "quebrado.xsd"
        quebrado.write_text("<nao-e-xsd/>", encoding="utf-8")
        modulo._validador.cache_clear()
        monkeypatch.setattr(modulo, "SCHEMA_PRINCIPAL", quebrado)
        try:
            with pytest.raises(ErroCTe, match="inválido"):
                modulo.validar(b"<CTe/>")
        finally:
            modulo._validador.cache_clear()

    def test_validar_ou_levantar_devolve_o_mesmo_xml(self, certificado: CertificadoA1) -> None:
        # Caminho que o gerador usa: o retorno é byte a byte o XML validado.
        xml = gerar_assinado(dados_cte(), certificado)

        assert validar_ou_levantar(xml) == xml


class TestGeradorDoCTe:
    def test_destinatario_pessoa_fisica_usa_cpf(self) -> None:
        dest = Parte(nome="PESSOA FISICA", cpf="11144477735")
        raiz = gerar(dados_cte(destinatario=dest))

        assert raiz.find(".//{*}dest/{*}CPF").text == "11144477735"
        assert raiz.find(".//{*}dest/{*}CNPJ") is None

    def test_parte_sem_cnpj_nem_cpf_recusa(self) -> None:
        with pytest.raises(ValueError, match="sem CNPJ nem CPF"):
            gerar(dados_cte(destinatario=Parte(nome="SEM DOCUMENTO")))

    def test_ie_do_tomador_sai_no_toma4(self) -> None:
        dest = Parte(nome="TOMADOR", cnpj=CNPJ, ie="123456789")
        raiz = gerar(dados_cte(papel_tomador=PapelTomador.OUTROS, destinatario=dest))
        toma4 = raiz.find(".//{*}ide/{*}toma4")

        assert toma4 is not None
        assert toma4.find("{*}IE").text == "123456789"

    def test_endereco_com_cep_emite_o_campo(self) -> None:
        # Só alcançável por chamada direta: `gerar()` sempre usa `com_cep=False`.
        raiz = etree.Element("raiz")
        _endereco(raiz, Parte(nome="X"), "enderEmit", com_cep=True)

        # `_endereco` monta tags sem namespace (`etree.SubElement(pai, tag)`).
        assert raiz.find("enderEmit/CEP").text == "74000000"

    def test_endereco_sem_cep_omite_o_campo(self) -> None:
        raiz = etree.Element("raiz")
        _endereco(raiz, Parte(nome="X"), "enderEmit", com_cep=False)

        assert raiz.find("enderEmit/CEP") is None


class _TransporteFalso:
    """Transporte SOAP falso: devolve bytes ou levanta, sem rede."""

    def __init__(self, resposta: bytes | Exception) -> None:
        self._resposta = resposta
        self.chamadas: list[dict] = []

    async def enviar(self, *, url: str, corpo: bytes, timeout_s: float) -> bytes:
        self.chamadas.append({"url": url, "corpo": corpo, "timeout_s": timeout_s})
        if isinstance(self._resposta, Exception):
            raise self._resposta
        return self._resposta


class _ClienteSefazFalso:
    """Dublê de `ClienteSefaz`: registra o pedido e devolve uma resposta montada."""

    def __init__(self, elemento: etree._Element) -> None:
        self._elemento = elemento
        self.chamadas: list[dict] = []

    async def chamar(self, **kwargs) -> RespostaSefaz:
        self.chamadas.append(kwargs)
        return RespostaSefaz(xml=b"<bruto/>", elemento=self._elemento)


_RETORNO_STATUS_CTE = (
    f'<retConsStatServCTe xmlns="{NS_CTE}"><cStat>107</cStat>'
    "<xMotivo>Servico em Operacao</xMotivo></retConsStatServCTe>"
)


class TestConsultasDoCTe:
    async def test_status_leva_cuf_e_o_wrapper_do_servico_de_cte(self) -> None:
        cliente = _ClienteSefazFalso(etree.fromstring(_RETORNO_STATUS_CTE.encode()))

        resposta = await consultar_status_cte(
            cliente, url="https://svrs.exemplo/cte/status", cuf="32"
        )

        assert resposta.cstat == "107"
        pedido = cliente.chamadas[0]
        assert pedido["ns_servico"] == NS_SERVICO_CTE
        assert pedido["elemento_dados"] == "cteDadosMsg"
        assert b"<cUF>32</cUF>" in pedido["xml_fiscal"]
        assert b"<xServ>STATUS</xServ>" in pedido["xml_fiscal"]

    async def test_situacao_leva_a_chave_e_nao_leva_cuf(self) -> None:
        cliente = _ClienteSefazFalso(etree.fromstring(_RETORNO_STATUS_CTE.encode()))
        chave = "52" + "1" * 42

        resposta = await consultar_situacao(
            cliente, url="https://svrs.exemplo/cte/consulta", chave=chave
        )

        assert resposta.cstat == "107"
        pedido = cliente.chamadas[0]
        assert f"<chCTe>{chave}</chCTe>".encode() in pedido["xml_fiscal"]
        assert b"cUF" not in pedido["xml_fiscal"]


# ---------------------------------------------------------------------------
# MDF-e: validador, consulta e gerador
# ---------------------------------------------------------------------------
class TestValidadorDoMDFe:
    def test_schema_ausente_recusa_apontando_o_caminho(self, monkeypatch, tmp_path: Path) -> None:
        import app.mdfe as modulo

        modulo._validador.cache_clear()
        monkeypatch.setattr(modulo, "SCHEMA_PRINCIPAL", tmp_path / "nao-existe.xsd")
        try:
            with pytest.raises(ErroMDFe, match="ausente"):
                modulo.validar(b"<MDFe/>")
        finally:
            modulo._validador.cache_clear()

    def test_schema_que_nao_compila_recusa_com_motivo(self, monkeypatch, tmp_path: Path) -> None:
        import app.mdfe as modulo

        quebrado = tmp_path / "quebrado.xsd"
        quebrado.write_text("<nao-e-xsd/>", encoding="utf-8")
        modulo._validador.cache_clear()
        monkeypatch.setattr(modulo, "SCHEMA_PRINCIPAL", quebrado)
        try:
            with pytest.raises(ErroMDFe, match="inválido"):
                modulo.validar(b"<MDFe/>")
        finally:
            modulo._validador.cache_clear()

    def test_xml_sem_assinatura_e_recusado_pelo_schema(self) -> None:
        xml = b'<?xml version="1.0" encoding="UTF-8"?>' + etree.tostring(gerar_mdfe(dados_mdfe()))

        with pytest.raises(ErroMDFe):
            validar_mdfe(xml)


class TestGeradorDoMDFe:
    def test_chave_de_nfe_com_tamanho_errado_recusa(self) -> None:
        descarga = Descarga("5208707", "GOIANIA", ("123",))

        with pytest.raises(ValueError, match="chave de NF-e inválida"):
            gerar_mdfe(dados_mdfe(descargas=(descarga,)))


class TestConsultaDoMDFe:
    async def test_pedido_nao_leva_cuf_e_usa_o_wrapper_de_mdfe(self) -> None:
        cliente = _ClienteSefazFalso(
            etree.fromstring(
                f'<retConsStatServMDFe xmlns="{NS_MDFE}"><cStat>107</cStat>'
                "<xMotivo>Servico em Operacao</xMotivo></retConsStatServMDFe>".encode()
            )
        )

        resposta = await consultar_status_mdfe(
            cliente, url="https://svrs.exemplo/mdfe/status", ambiente="2"
        )

        assert resposta.cstat == "107"
        pedido = cliente.chamadas[0]
        assert pedido["ns_servico"] == NS_SERVICO_MDFE
        assert pedido["elemento_dados"] == "mdfeDadosMsg"
        assert b"<tpAmb>2</tpAmb>" in pedido["xml_fiscal"]
        assert b"cUF" not in pedido["xml_fiscal"]


# ---------------------------------------------------------------------------
# NFS-e: constantes, credenciais, fábrica, evento, roteamento, schemas e transporte
# ---------------------------------------------------------------------------
class TestLeiauteDaNFSe:
    def test_producao_ate_30_de_novembro_usa_leiaute_anterior(self) -> None:
        assert leiaute(AmbienteFiscal.PRODUCAO, quando=datetime(2026, 11, 30)) == LEIAUTE_ANTERIOR

    def test_producao_a_partir_de_1_de_dezembro_usa_nt009(self) -> None:
        assert leiaute(AmbienteFiscal.PRODUCAO, quando=datetime(2026, 12, 1)) == LEIAUTE_NT009

    def test_data_sem_fuso_e_lida_no_fuso_de_brasilia(self) -> None:
        # `datetime` ingênuo não pode ser interpretado como UTC: 01/12 00:00 em Brasília
        # já é a virada da NT 009, e é isso que a função precisa responder.
        assert leiaute(AmbienteFiscal.PRODUCAO, quando=datetime(2026, 12, 1, 0, 0)) == LEIAUTE_NT009
        assert (
            leiaute(AmbienteFiscal.PRODUCAO, quando=datetime(2026, 11, 30, 23, 0))
            == LEIAUTE_ANTERIOR
        )


class TestCredencialMunicipal:
    def test_campo_de_segredo_desconhecido_recusa(self) -> None:
        credencial = CredencialMunicipalTenant(tenant_id=uuid.uuid4(), codigo_ibge="5208707")

        with pytest.raises(ValueError, match="desconhecido"):
            segredo(credencial, "certificado_senha", cofre=object())


class TestFabricaDeDrivers:
    class _TransporteFalso:
        async def enviar(self, *, url: str, corpo: bytes, encoding: str) -> bytes:
            return b"<x/>"

    def test_com_certificado_a_fabrica_injeta_assinador(self) -> None:
        municipio = MunicipioParaDriver(
            codigo_ibge="5208707",
            provedor="ginfes",
            url="https://provedor.example/nfse",
            namespace="http://www.abrasf.org.br/nfse.xsd",
            fonte_url="https://www.goiania.go.gov.br/nfse/manual.pdf",
        )

        driver = criar_driver(municipio, transporte=self._TransporteFalso(), certificado=object())

        assert driver._assinador is not None


class TestEventoDaNFSe:
    CHAVE = "355030" + "11222333000181" + "0" * 30

    def test_sequencia_fora_da_faixa_recusa(self) -> None:
        with pytest.raises(ErroDeEvento, match="sequência"):
            id_evento_registrado(self.CHAVE, "101101", 0)

        with pytest.raises(ErroDeEvento, match="sequência"):
            id_evento_registrado(self.CHAVE, "101101", 1000)

    def test_tipo_de_evento_sem_seis_digitos_recusa(self) -> None:
        with pytest.raises(ErroDeEvento, match="6 dígitos"):
            id_evento_registrado(self.CHAVE, "1011", 1)

    def test_ver_aplic_com_mais_de_20_caracteres_recusa(self) -> None:
        pedido = PedidoCancelamento(
            chave=self.CHAVE,
            cnpj_autor=CNPJ,
            c_motivo="1",
            x_motivo="Cancelamento solicitado pelo cliente",
            ver_aplic="v" * 21,
        )

        with pytest.raises(ErroDeEvento, match="verAplic"):
            pedido.validar()


class TestRoteamentoDaNFSe:
    def test_competencia_nao_numerica_nao_dispara_a_obrigacao_do_simples(self) -> None:
        decisao = decidir_rota(
            aderente_emissor_nacional=False,
            aderente_confirmado=True,
            simples_nacional=True,
            optante_mei=False,
            competencia="20XX-01",
            ambiente="homologacao",
        )

        # Competência ilegível não vira obrigação nacional: cai no parâmetro municipal.
        assert decisao.rota == "municipal"
        assert decisao.permitido is False

    def test_competencia_com_mes_invalido_nao_dispara_a_obrigacao_do_simples(self) -> None:
        decisao = decidir_rota(
            aderente_emissor_nacional=False,
            aderente_confirmado=True,
            simples_nacional=True,
            optante_mei=False,
            competencia="2026-13",
            ambiente="homologacao",
        )

        assert decisao.rota == "municipal"
        assert decisao.permitido is False


class TestContratoDeEmissao:
    def test_referencia_externa_em_branco_vira_none(self) -> None:
        pedido = EmissaoIn(valor="10.00", descricao="Servico", referencia_externa="   ")

        assert pedido.referencia_externa is None

    def test_referencia_externa_preenchida_e_preservada(self) -> None:
        pedido = EmissaoIn(valor="10.00", descricao="Servico", referencia_externa="venda-1")

        assert pedido.referencia_externa == "venda-1"


class TestTransporteDaSefin:
    def test_cliente_usa_o_contexto_tls_do_certificado(self, monkeypatch) -> None:
        visto: dict = {}

        class ClienteFalso:
            def __init__(self, **kwargs) -> None:
                visto.update(kwargs)

        class CertificadoFalso:
            def __init__(self, contexto: ssl.SSLContext) -> None:
                self._contexto = contexto

            def ssl_context(self) -> ssl.SSLContext:
                return self._contexto

        monkeypatch.setattr(httpx, "Client", ClienteFalso)
        contexto = ssl.create_default_context()

        criar_cliente(CertificadoFalso(contexto))

        # `verify` recebe o contexto pronto (mTLS + raízes), não `True` nem caminho de PEM.
        assert visto["verify"] is contexto

    async def test_timeout_de_conexao_e_indisponivel(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("tempo esgotado")

        with (
            httpx.Client(transport=httpx.MockTransport(handler)) as cliente,
            pytest.raises(ErroSefin) as capturado,
        ):
            executar(
                cliente,
                "POST",
                "https://sefin.nfse.gov.br/SefinNacional/dps",
                operacao="dps",
            )

        assert capturado.value.tipo is TipoErroFiscal.INDISPONIVEL
        assert "tempo esgotado" in capturado.value.resumo

    async def test_connect_error_sem_marca_de_tls_e_indisponivel(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("conexao recusada")

        with (
            httpx.Client(transport=httpx.MockTransport(handler)) as cliente,
            pytest.raises(ErroSefin) as capturado,
        ):
            executar(
                cliente,
                "POST",
                "https://sefin.nfse.gov.br/SefinNacional/dps",
                operacao="dps",
            )

        assert capturado.value.tipo is TipoErroFiscal.INDISPONIVEL
        assert "não foi possível conectar" in capturado.value.resumo


# ---------------------------------------------------------------------------
# DANFSe: parser e renderizador
# ---------------------------------------------------------------------------
class TestParserDoDANFSe:
    def test_valor_nao_numerico_e_mostrado_como_veio(self) -> None:
        # Não inventa número: se o XML traz texto, o PDF mostra o texto e quem confere vê.
        xml = (
            '<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">'
            "<infNFSe><DPS><infDPS><valores><vServPrest><vServ>abc</vServ>"
            "</vServPrest></valores></infDPS></DPS></infNFSe></NFSe>"
        )

        assert parse_danfse(xml).totais.valor_servico == "abc"

    def test_xml_sem_inf_nfse_devolve_chave_vazia(self) -> None:
        raiz = etree.fromstring(
            b'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse"><outra/></NFSe>'
        )
        dados = parse_danfse(b'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse"/>')

        assert extrair_chave(raiz) == ""
        assert dados.chave_acesso == ""


class TestRenderizadorDoDANFSe:
    def test_palavra_maior_que_a_largura_nao_e_cortada(self) -> None:
        # `_quebrar` NÃO parte palavra: uma palavra de 130 caracteres vira uma linha só,
        # mesmo passando da largura — cortar palavra é pior que estourar a coluna.
        assert _quebrar("X" * 130, 120) == ["X" * 130]

    def test_quebra_entre_palavras_respeita_a_largura(self) -> None:
        assert _quebrar("A" * 100 + " " + "B" * 30, 120) == ["A" * 100, "B" * 30]

    def test_chave_e_agrupada_de_quatro_em_quatro(self) -> None:
        assert _formatar_chave("12345678") == "1234 5678"

    def test_issqn_nao_sujeito_imprime_a_ressalva(self) -> None:
        dados = DanfseData(numero="9", chave_acesso="")
        dados.issqn = TributacaoIssqn(trib_issqn="4", nao_sujeito=True)

        pdf = gerar_danfse(dados)

        assert pdf.startswith(b"%PDF")
        texto = "\n".join(pagina.extract_text() or "" for pagina in PdfReader(BytesIO(pdf)).pages)
        assert "NÃO SUJEITO" in texto
