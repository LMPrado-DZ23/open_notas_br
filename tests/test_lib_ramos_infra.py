"""Bordas de infraestrutura: navegação em XML, helpers de contexto, assinatura e API.

Três famílias:

- `xml_util`: entrada que não é elemento (comentário), caminho com parte vazia e nó de outra
  árvore;
- `regras.base`: acesso pela raiz, código de regra duplicado e texto vazio convertido em `None`;
- `assinatura` e `api`: ramos de dependência opcional e a tradução de exceção em HTTP, que só
  aparecem quando o extra falta ou quando a falha vem de outro lugar.
"""

from __future__ import annotations

import base64
import datetime
import sys
from xml.etree import ElementTree as ET

import pytest

from notasbr import Severidade
from notasbr.erros import ArquivoGrandeDemais
from notasbr.regras.assinatura import verificacao_criptografica
from notasbr.regras.base import Contexto, regra, texto_ou_none
from notasbr.xml_util import (
    caminho_de,
    filhos,
    local,
    mapa_de_pais,
    namespace,
    navegar,
    parse_seguro,
)
from tests.construir import nfe, transformar


def _contexto(xml: bytes, *, bytes_originais: bytes | None = None) -> Contexto:
    raiz = parse_seguro(xml)
    corpo = navegar(raiz, "NFe/infNFe")
    assert corpo is not None
    return Contexto(raiz=raiz, tipo="nfe", corpo=corpo, bytes_originais=bytes_originais)


def _motivo_da_pulada(ctx: Contexto, codigo: str) -> str:
    return next(p.motivo for p in ctx.puladas if p.codigo == codigo)


class TestXmlUtilBordas:
    def test_comentario_nao_tem_nome_local_nem_namespace(self) -> None:
        """Comentário e PI têm `tag` que não é string; a navegação devolve vazio."""
        raiz = parse_seguro(b"<a/>")
        raiz.append(ET.Comment("nota do emissor"))
        comentario = next(iter(raiz))

        assert local(comentario.tag) == ""
        assert namespace(comentario.tag) is None

    def test_filhos_de_none_e_lista_vazia(self) -> None:
        assert filhos(None, "det") == []

    def test_navegar_ignora_parte_vazia_do_caminho(self) -> None:
        """`NFe//infNFe` é tolerado como `NFe/infNFe`: parte vazia não quebra a navegação."""
        raiz = parse_seguro(nfe())

        assert navegar(raiz, "NFe//infNFe/ide") is not None

    def test_caminho_de_elemento_de_outra_arvore_para_na_raiz(self) -> None:
        """Elemento que não pertence à árvore não vira caminho inventado: sobra só a raiz."""
        raiz = parse_seguro(nfe())
        estranho = parse_seguro(b"<outro/>")

        assert caminho_de(raiz, estranho, mapa_de_pais(raiz)) == "nfeProc"


class TestContexto:
    def test_le_pela_raiz_e_pelo_corpo(self) -> None:
        ctx = _contexto(nfe())

        assert ctx.txt_raiz("protNFe/infProt/nProt") == "135250000000001"
        assert ctx.txt_raiz("protNFe/infProt/naoExiste") is None
        assert ctx.texto_sim_nao("ide/indFinal") == "1"
        assert ctx.texto_sim_nao("ide/naoExiste") is None
        assert ctx.caminho() == "nfeProc/NFe/infNFe"

    def test_codigo_de_regra_duplicado_e_recusado(self) -> None:
        """Duas regras com o mesmo código quebrariam o relatório; o registro recusa antes."""
        with pytest.raises(RuntimeError, match="CHAVE-DV-001"):
            regra("CHAVE-DV-001", "duplicada")(lambda ctx: None)


class TestTextoOuNone:
    def test_vazio_vira_none(self) -> None:
        raiz = parse_seguro(b"<a><b> x </b><c>   </c></a>")

        assert texto_ou_none(raiz, "b") == "x"
        assert texto_ou_none(raiz, "c") is None
        assert texto_ou_none(None, "b") is None


class TestAssinaturaSemExtra:
    def test_import_indisponivel_pula_a_verificacao(self, monkeypatch) -> None:
        """Sem `signxml` a verificação é pulada com motivo instalável — nunca aprovada."""
        monkeypatch.setitem(sys.modules, "signxml", None)
        ctx = _contexto(nfe())

        verificacao_criptografica(ctx)

        assert ctx.achados == []
        assert "notasbr[assinatura]" in _motivo_da_pulada(ctx, "ASSIN-004")


def _certificado_der() -> bytes:
    """Certificado autoassinado descartável, gerado no teste (nenhum certificado real)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Teste notasbr")])
    inicio = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(inicio)
        .not_valid_after(inicio + datetime.timedelta(days=1))
        .sign(chave, hashes.SHA256())
    )
    return certificado.public_bytes(serialization.Encoding.DER)


class TestAssinaturaSemBytesOriginais:
    def test_sem_bytes_originais_reconstroi_a_arvore_e_reporta_a_falha(self) -> None:
        """Sem os bytes originais a árvore é re-serializada; a falha de C14N vira erro.

        O caminho normal da auditoria sempre tem `bytes_originais`, então este ramo só é
        exercitado chamando a regra com um `Contexto` sem eles. O documento traz um
        certificado decodificável e uma assinatura impossível: o desfecho precisa ser erro
        nomeado, não exceção vazando do motor.
        """
        der = _certificado_der()

        def mutar(raiz: ET.Element) -> None:
            assinatura = next(e for e in raiz.iter() if local(e.tag) == "Signature")
            certificado = ET.SubElement(assinatura, "X509Certificate")
            certificado.text = base64.b64encode(der).decode()

        ctx = _contexto(transformar(nfe(), mutar))

        verificacao_criptografica(ctx)

        erros = [a for a in ctx.achados if a.codigo == "ASSIN-004"]
        assert len(erros) == 1
        assert erros[0].severidade is Severidade.ERRO
        assert erros[0].detalhe["erro"], "a falha precisa nomear a exceção da biblioteca"


class TestApiArquivoGrande:
    def test_arquivo_grande_demais_vira_413(self, monkeypatch) -> None:
        """A tradução `ArquivoGrandeDemais` -> 413 é contrato da API.

        Pelo caminho HTTP normal o limite da rota e o do parser são o mesmo valor, então a
        exceção só aparece se o parser discordar da rota. O teste fixa a tradução.
        """
        pytest.importorskip("fastapi")
        pytest.importorskip("httpx")
        from fastapi.testclient import TestClient

        import notasbr.api as api

        def estourar(*args, **kwargs):
            raise ArquivoGrandeDemais("arquivo tem 9999 bytes, acima do limite de 10 bytes")

        monkeypatch.setattr(api, "auditar_bytes", estourar)
        cliente = TestClient(api.criar_app())

        resposta = cliente.post(
            "/v1/auditar", files={"arquivo": ("nota.xml", b"<x/>", "application/xml")}
        )

        assert resposta.status_code == 413
        assert "acima do limite" in resposta.json()["detail"]
