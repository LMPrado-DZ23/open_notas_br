"""Testes diretos do serviço de emissão.

Os testes HTTP cobrem o caminho feliz; aqui o alvo são os caminhos que só
acontecem em produção:

- timeout ambíguo (a nota pode ter sido processada) e a recuperação;
- rejeição e falha, com o evento registrado e o status correto;
- pré-requisitos ausentes (certificado, configuração fiscal);
- idempotência no nível do serviço.

Chamar `emitir` direto é o que permite controlar o adapter e inspecionar o estado
persistido sem passar por HTTP.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings, get_settings
from app.db.models.enums import StatusFatura
from app.db.models.invoice import FiscalDocument, Invoice, InvoiceEvent
from app.db.models.tenant import Tenant
from app.nfse import servico
from app.nfse.adapter import RespostaEmissao, SefinMockAdapter
from app.nfse.errors import ErroSefin, MensagemSefin
from app.nfse.errors import TipoErroFiscal as TipoErro
from sqlalchemy import select

from tests.test_fase2_certificado import SENHA, gerar_pfx


@pytest.fixture
async def preparado(cliente, app_teste, sessao_db):
    """Tenant com config fiscal e certificado, e o objeto ORM pronto."""
    resposta = await cliente.post(
        "/v1/tenants", json={"slug": "servico-tenant", "nome": "Serviço LTDA"}
    )
    dados = resposta.json()
    cabecalho = {"X-API-Key": dados["api_key"]}

    app_teste.dependency_overrides[get_settings] = lambda: Settings(
        environment="test", nfse_adapter="mock"
    )
    await cliente.put(
        "/v1/me/config-fiscal",
        json={
            "municipio_ibge": "3550308",
            "uf": "SP",
            "ambiente": "homologacao",
            "codigo_tributacao_nacional": "010701",
            "serie_dps": "1",
            "aliquota_iss": 0.05,
        },
        headers=cabecalho,
    )
    await cliente.post(
        "/v1/me/certificados",
        files={"arquivo": ("c.pfx", gerar_pfx(), "application/x-pkcs12")},
        data={"senha": SENHA.decode(), "apelido": "a1"},
        headers=cabecalho,
    )

    tenant = (
        await sessao_db.execute(select(Tenant).where(Tenant.slug == "servico-tenant"))
    ).scalar_one()

    yield tenant, dados

    app_teste.dependency_overrides.clear()


def nova_fatura(tenant: Tenant, chave: str, valor: str = "85.00") -> Invoice:
    return Invoice(
        tenant_id=tenant.id,
        idempotency_key=chave,
        status=StatusFatura.PENDENTE,
        valor_servico=valor,
        descricao_servico="Corte de cabelo",
        competencia="2026-11",
    )


class TestCaminhoFeliz:
    async def test_emite_e_persiste(self, sessao_db, preparado) -> None:
        tenant, _ = preparado
        fatura = nova_fatura(tenant, "servico-ok-001")
        sessao_db.add(fatura)
        await sessao_db.flush()

        documento = await servico.emitir(sessao_db, tenant, fatura, adapter=SefinMockAdapter())
        await sessao_db.commit()

        assert documento.chave is not None
        assert len(documento.chave) == 50
        # A NFS-e devolvida pela SEFIN não é assinada por nós: quem assina é a
        # DPS enviada. O que precisa existir aqui é o documento autorizado.
        assert documento.xml_autorizado and "infNFSe" in documento.xml_autorizado
        assert fatura.status == StatusFatura.AUTORIZADA

    async def test_segunda_chamada_nao_reemite(self, sessao_db, preparado) -> None:
        tenant, _ = preparado
        fatura = nova_fatura(tenant, "servico-idem-001")
        sessao_db.add(fatura)
        await sessao_db.flush()

        adapter = SefinMockAdapter()
        primeiro = await servico.emitir(sessao_db, tenant, fatura, adapter=adapter)
        segundo = await servico.emitir(sessao_db, tenant, fatura, adapter=adapter)
        await sessao_db.commit()

        assert primeiro.id == segundo.id
        assert len(adapter.chamadas) == 1, "a segunda chamada não pode ir à SEFIN"

    async def test_registra_evento_de_autorizacao(self, sessao_db, preparado) -> None:
        tenant, _ = preparado
        fatura = nova_fatura(tenant, "servico-evento-001")
        sessao_db.add(fatura)
        await sessao_db.flush()

        await servico.emitir(sessao_db, tenant, fatura, adapter=SefinMockAdapter())
        await sessao_db.commit()

        eventos = (
            (
                await sessao_db.execute(
                    select(InvoiceEvent).where(InvoiceEvent.invoice_id == fatura.id)
                )
            )
            .scalars()
            .all()
        )
        # O evento é a trilha de auditoria: basta existir registro para a fatura.
        assert eventos

    async def test_numero_da_dps_avanca(self, sessao_db, preparado) -> None:
        tenant, _ = preparado
        numeros = []
        for indice in range(2):
            fatura = nova_fatura(tenant, f"servico-num-{indice:03d}")
            sessao_db.add(fatura)
            await sessao_db.flush()
            documento = await servico.emitir(sessao_db, tenant, fatura, adapter=SefinMockAdapter())
            numeros.append(servico.extrair_id(documento.xml_assinado.encode("utf-8")))
        await sessao_db.commit()
        assert numeros[0] != numeros[1]


class TestPreRequisitos:
    async def test_sem_certificado(self, sessao_db, cliente, app_teste) -> None:
        criado = await cliente.post(
            "/v1/tenants", json={"slug": "sem-cert", "nome": "Sem Cert LTDA"}
        )
        cabecalho = {"X-API-Key": criado.json()["api_key"]}
        await cliente.put(
            "/v1/me/config-fiscal",
            json={
                "municipio_ibge": "3550308",
                "uf": "SP",
                "ambiente": "homologacao",
                "codigo_tributacao_nacional": "010701",
                "serie_dps": "1",
            },
            headers=cabecalho,
        )
        tenant = (
            await sessao_db.execute(select(Tenant).where(Tenant.slug == "sem-cert"))
        ).scalar_one()

        fatura = nova_fatura(tenant, "servico-semcert-001")
        sessao_db.add(fatura)
        await sessao_db.flush()

        with pytest.raises(servico.CertificadoAusente, match="certificado"):
            await servico.emitir(sessao_db, tenant, fatura, adapter=SefinMockAdapter())

    async def test_sem_configuracao_fiscal(self, sessao_db, cliente) -> None:
        await cliente.post("/v1/tenants", json={"slug": "sem-config", "nome": "Sem Config LTDA"})
        tenant = (
            await sessao_db.execute(select(Tenant).where(Tenant.slug == "sem-config"))
        ).scalar_one()
        fatura = nova_fatura(tenant, "servico-semcfg-001")
        sessao_db.add(fatura)
        await sessao_db.flush()

        with pytest.raises(servico.ConfiguracaoFiscalAusente, match="configuração"):
            await servico.emitir(sessao_db, tenant, fatura, adapter=SefinMockAdapter())


class AdapterFalho(SefinMockAdapter):
    """Adapter controlável: falha de um jeito específico."""

    def __init__(self, erro: ErroSefin, *, chave_dps: str | None = None) -> None:
        super().__init__()
        self.erro = erro
        self.chave_dps = chave_dps
        self.consultas: list[str] = []

    def emitir(self, dps_assinada: bytes) -> RespostaEmissao:
        raise self.erro

    def consultar_dps(self, id_dps: str) -> str | None:
        self.consultas.append(id_dps)
        return self.chave_dps


class TestFalhas:
    async def test_rejeicao_marca_fatura_e_evento(self, sessao_db, preparado) -> None:
        tenant, _ = preparado
        fatura = nova_fatura(tenant, "servico-rejeita-001")
        sessao_db.add(fatura)
        await sessao_db.flush()

        erro = ErroSefin(
            tipo=TipoErro.REJEICAO,
            resumo="a SEFIN recusou a DPS",
            mensagens=[MensagemSefin(codigo="E001", descricao="rejeitada no teste")],
            http_status=400,
        )
        with pytest.raises(ErroSefin):
            await servico.emitir(sessao_db, tenant, fatura, adapter=AdapterFalho(erro))
        await sessao_db.commit()

        assert fatura.status == StatusFatura.REJEITADA
        eventos = (
            (
                await sessao_db.execute(
                    select(InvoiceEvent).where(InvoiceEvent.invoice_id == fatura.id)
                )
            )
            .scalars()
            .all()
        )
        assert eventos, "rejeição precisa deixar evento para auditoria"

    async def test_falha_de_autenticacao_marca_erro(self, sessao_db, preparado) -> None:
        tenant, _ = preparado
        fatura = nova_fatura(tenant, "servico-auth-001")
        sessao_db.add(fatura)
        await sessao_db.flush()

        erro = ErroSefin(
            tipo=TipoErro.AUTENTICACAO,
            resumo="a SEFIN recusou a DPS",
            mensagens=[MensagemSefin(codigo=None, descricao="403")],
            http_status=403,
        )
        with pytest.raises(ErroSefin):
            await servico.emitir(sessao_db, tenant, fatura, adapter=AdapterFalho(erro))
        await sessao_db.commit()

        assert fatura.status == StatusFatura.ERRO

    async def test_recuperacao_devolve_nota_quando_dps_existe(self) -> None:
        """`_tentar_recuperar` é o caminho que evita nota duplicada após timeout."""
        chave = "3550308" + "9" * 42
        resposta = RespostaEmissao(
            chave_acesso=chave,
            nfse_xml=b'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01"/>',
        )

        class AdapterRecuperavel:
            def __init__(self) -> None:
                self.consultas: list[str] = []

            def consultar_dps(self, id_dps: str) -> str | None:
                self.consultas.append(id_dps)
                return chave

            def consultar_nfse(self, chave_consultada: str) -> RespostaEmissao:
                assert chave_consultada == chave
                return resposta

        adapter = AdapterRecuperavel()
        erro = ErroSefin(
            tipo=TipoErro.AMBIGUO,
            resumo="timeout",
            mensagens=[MensagemSefin(codigo=None, descricao="timeout")],
        )
        recuperada = await servico._tentar_recuperar(adapter, "DPS123", erro)

        assert recuperada is not None
        assert recuperada.chave_acesso == chave
        assert adapter.consultas == ["DPS123"]

    async def test_recuperacao_sem_dps_devolve_none(self) -> None:
        class AdapterSemNota:
            def consultar_dps(self, id_dps: str) -> str | None:
                return None

            def consultar_nfse(self, chave_consultada: str) -> RespostaEmissao:  # pragma: no cover
                raise AssertionError("não deveria consultar a NFS-e")

        erro = ErroSefin(
            tipo=TipoErro.AMBIGUO,
            resumo="timeout",
            mensagens=[MensagemSefin(codigo=None, descricao="timeout")],
        )
        assert await servico._tentar_recuperar(AdapterSemNota(), "DPS1", erro) is None

    async def test_recuperacao_com_falha_na_consulta_devolve_none(self) -> None:
        class AdapterQuebrado:
            def consultar_dps(self, id_dps: str) -> str | None:
                raise ErroSefin(
                    tipo=TipoErro.INDISPONIVEL,
                    resumo="fora do ar",
                    mensagens=[],
                )

            def consultar_nfse(self, chave_consultada: str) -> RespostaEmissao:  # pragma: no cover
                raise AssertionError("não deveria consultar a NFS-e")

        erro = ErroSefin(
            tipo=TipoErro.AMBIGUO,
            resumo="timeout",
            mensagens=[MensagemSefin(codigo=None, descricao="timeout")],
        )
        assert await servico._tentar_recuperar(AdapterQuebrado(), "DPS1", erro) is None

    async def test_timeout_ambiguo_sem_nota_propaga_erro(self, sessao_db, preparado) -> None:
        tenant, _ = preparado
        fatura = nova_fatura(tenant, "servico-ambiguo-002")
        sessao_db.add(fatura)
        await sessao_db.flush()

        # AMBIGUO é o tipo cuja propriedade `pode_ter_sido_processada` é True.
        ambiguo = ErroSefin(
            tipo=TipoErro.AMBIGUO,
            resumo="tempo esgotado ao enviar a DPS",
            mensagens=[MensagemSefin(codigo=None, descricao="timeout")],
            http_status=None,
        )
        adapter = AdapterFalho(ambiguo, chave_dps=None)

        with pytest.raises(ErroSefin):
            await servico.emitir(sessao_db, tenant, fatura, adapter=adapter)
        await sessao_db.commit()
        assert adapter.consultas, "mesmo sem nota, deve ter tentado consultar"


class TestInformacoes:
    async def test_documento_guarda_ambiente(self, sessao_db, preparado) -> None:
        tenant, _ = preparado
        fatura = nova_fatura(tenant, "servico-amb-001")
        sessao_db.add(fatura)
        await sessao_db.flush()

        documento = await servico.emitir(sessao_db, tenant, fatura, adapter=SefinMockAdapter())
        await sessao_db.commit()
        assert documento.ambiente.value == "homologacao"

    async def test_documento_aponta_para_fatura(self, sessao_db, preparado) -> None:
        tenant, _ = preparado
        fatura = nova_fatura(tenant, "servico-link-001")
        sessao_db.add(fatura)
        await sessao_db.flush()

        documento = await servico.emitir(sessao_db, tenant, fatura, adapter=SefinMockAdapter())
        await sessao_db.commit()

        encontrado = (
            (
                await sessao_db.execute(
                    select(FiscalDocument).where(FiscalDocument.invoice_id == fatura.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(encontrado) == 1
        assert encontrado[0].id == documento.id
