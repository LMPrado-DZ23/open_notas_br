"""Mapeamento do ORM para a fábrica: ambiente, namespace e versão de SOAP."""

from __future__ import annotations

import pytest
from app.db.models.municipio import EncodingXML, MunicipioNFSe, ProvedorNFSe
from app.nfse.drivers import ErroDeDriver
from app.nfse.drivers_factory import criar_driver, de_municipio

NS = "http://www.abrasf.org.br/nfse.xsd"


def linha(**extra) -> MunicipioNFSe:
    base = {
        "codigo_ibge": "5208707",
        "nome": "Goiânia",
        "uf": "GO",
        "provedor": ProvedorNFSe.GINFES,
        "versao_layout": "2.04",
        "url_homologacao": "https://homolog.example/nfse",
        "url_producao": "https://prod.example/nfse",
        "namespace_xml": NS,
        "exige_credencial_municipal": True,
        "assina_rps": True,
        "assina_lote": False,
        "encoding": EncodingXML.UTF8,
        "homologado": False,
        "fonte_url": "https://www.goiania.go.gov.br/nfse/manual.pdf",
    }
    base.update(extra)
    return MunicipioNFSe(**base)


class TestAmbiente:
    def test_homologacao_usa_url_de_homologacao(self) -> None:
        m = de_municipio(linha(), ambiente="homologacao")
        assert m.url == "https://homolog.example/nfse"

    def test_producao_usa_url_de_producao(self) -> None:
        m = de_municipio(linha(), ambiente="producao")
        assert m.url == "https://prod.example/nfse"

    def test_padrao_e_homologacao(self) -> None:
        # Emitir em produção por omissão é irreversível; o default não pode ser produção.
        assert de_municipio(linha()).url == "https://homolog.example/nfse"


class TestCampos:
    def test_enums_viram_texto(self) -> None:
        m = de_municipio(linha())
        assert m.provedor == "ginfes"
        assert m.encoding == "UTF-8"

    def test_assinaturas_vem_do_cadastro(self) -> None:
        m = de_municipio(linha(assina_rps=True, assina_lote=False))
        assert m.assina_rps is True
        assert m.assina_lote is False

    def test_versao_de_soap_e_explicita(self) -> None:
        assert de_municipio(linha()).versao_soap == "1.2"
        assert de_municipio(linha(), versao_soap="1.1").versao_soap == "1.1"


class TestGuarda:
    def test_sem_namespace_recusa(self) -> None:
        with pytest.raises(ErroDeDriver, match="namespace_xml"):
            de_municipio(linha(namespace_xml=None))

    def test_sem_url_do_ambiente_chega_nula_na_fabrica(self) -> None:
        # de_municipio não inventa URL: devolve None e a fábrica recusa com motivo.
        m = de_municipio(linha(url_homologacao=None))
        assert m.url is None


class TestPontaAPontaLocal:
    """Cadastro -> driver -> emissão, com transporte falso.

    Prova que o caminho funciona para um município cadastrado com URL e fonte. **Não**
    prova que o provedor aceita: isso exige contato real, que não existe nesta sessão.
    """

    RPS = (
        f'<EnviarLoteRpsEnvio xmlns="{NS}"><LoteRps Id="lote1"><ListaRps><Rps>'
        f'<InfDeclaracaoPrestacaoServico Id="rps1"><Competencia>2026-11-01</Competencia>'
        f"</InfDeclaracaoPrestacaoServico></Rps></ListaRps></LoteRps></EnviarLoteRpsEnvio>"
    ).encode()

    RESPOSTA = (
        f'<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"><soap:Body>'
        f'<EnviarLoteRpsResposta xmlns="{NS}"><Protocolo>P-1</Protocolo>'
        f"</EnviarLoteRpsResposta></soap:Body></soap:Envelope>"
    ).encode()

    async def test_municipio_cadastrado_emite_ate_o_transporte(self) -> None:
        enviados: list[dict] = []

        class Transporte:
            async def enviar(self, *, url: str, corpo: bytes, encoding: str) -> bytes:
                enviados.append({"url": url, "corpo": corpo, "encoding": encoding})
                return self_resposta

        self_resposta = self.RESPOSTA
        driver = criar_driver(de_municipio(linha(assina_lote=False)), transporte=Transporte())
        resultado = await driver.emitir_rps(dados={"xml": self.RPS})

        assert resultado.sucesso is True
        assert resultado.protocolo == "P-1"
        assert enviados[0]["url"] == "https://homolog.example/nfse"
        assert b"EnviarLoteRpsEnvio" in enviados[0]["corpo"]

    async def test_municipio_sem_fonte_nao_emite(self) -> None:
        class Transporte:
            async def enviar(self, *, url: str, corpo: bytes, encoding: str) -> bytes:
                raise AssertionError("não deveria chamar o transporte")

        with pytest.raises(ErroDeDriver, match="fonte"):
            criar_driver(de_municipio(linha(fonte_url="")), transporte=Transporte())
