"""Ramos de `app/api/v1/emissoes.py` e `app/nfse/servico.py` que faltavam à suíte.

O mapa de cobertura da suíte completa mostrava dois arquivos abaixo do piso do projeto:

- `app/api/v1/emissoes.py` em 47% — sem DANFSe, sem representação, sem catálogo de eventos,
  sem nenhum dos ramos de erro do `POST /v1/emissoes` (config ambígua, rota bloqueada,
  certificado ambíguo, erro da SEFIN) e sem o caminho "fatura já existe e não está autorizada";
- `app/nfse/servico.py` em 90% — sem webhook que falha, sem `ind_dest` do IBS/CBS, sem
  desconto maior que o valor, sem o preflight de rota bloqueando e sem a recuperação de
  emissão após timeout ambíguo.

O arquivo cobre os dois níveis, de propósito:

1. **HTTP com app e banco reais** (`cliente`) onde o comportamento é observável pela API —
   status, corpo, PDF, trilha em `invoice_events`. É o nível que prova o contrato.
2. **Chamada direta do handler/serviço com sessão dublê** onde o estado necessário não é
   alcançável pela API sem inventar dado fiscal (documento sem XML autorizado, `IntegrityError`
   na criação da fatura, `ErroDps` na serialização, timeout ambíguo já processado). Aqui o
   dublê só substitui a sessão e o adapter — nada de rede, nada de `unittest.mock` mágico.

Nada de código de produção foi alterado para caber no teste: onde um ramo depende de falha
externa, o dublê é instalado por `monkeypatch` no teste.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from app.api.v1 import emissoes
from app.core.config import Settings, get_settings
from app.db.models.enums import AmbienteFiscal, StatusFatura, TipoDocumento
from app.db.models.invoice import FiscalDocument, Invoice, InvoiceEvent
from app.nfse import servico as emissao_service
from app.nfse.adapter import RespostaEmissao, SefinMockAdapter
from app.nfse.errors import ErroSefin, TipoErroFiscal
from app.nfse.resiliencia import registro_padrao
from app.nfse.schemas import EmissaoIn
from sqlalchemy.exc import IntegrityError

from tests.test_danfse import NFSE_XML
from tests.test_fase2_certificado import SENHA, gerar_pfx

MUNICIPIO = "5200258"
MUNICIPIO_B = "3550308"
MOTIVO = "Cliente desistiu do servico antes da execucao"
CHAVE_MOCK = "1" * 50


# ---------------------------------------------------------------------------
# Apoio
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def circuito_zerado():
    """Circuito é global ao processo: teste que provoca falha não pode contaminar o seguinte."""
    registro_padrao.resetar()
    yield
    registro_padrao.resetar()


def cabecalho(tenant: dict[str, Any]) -> dict[str, str]:
    return {"X-API-Key": tenant["api_key"]}


async def criar_tenant(cliente, slug: str) -> dict[str, Any]:
    resposta = await cliente.post("/v1/tenants", json={"slug": slug, "nome": f"{slug} LTDA"})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


async def configurar(
    cliente, tenant: dict[str, Any], *, municipio: str = MUNICIPIO, **extra: Any
) -> dict[str, Any]:
    corpo: dict[str, Any] = {
        "municipio_ibge": municipio,
        "uf": "GO",
        "ambiente": "homologacao",
        "codigo_tributacao_nacional": "010701",
        "serie_dps": "1",
        "aliquota_iss": 0.05,
        "simples_nacional": False,
    }
    corpo.update(extra)
    resposta = await cliente.put("/v1/me/config-fiscal", json=corpo, headers=cabecalho(tenant))
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


async def enviar_certificado(cliente, tenant: dict[str, Any]) -> dict[str, Any]:
    resposta = await cliente.post(
        "/v1/me/certificados",
        files={"arquivo": ("c.pfx", gerar_pfx(), "application/x-pkcs12")},
        data={"senha": SENHA.decode(), "apelido": "a1"},
        headers=cabecalho(tenant),
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def corpo_emissao(chave: str, **extra: Any) -> dict[str, Any]:
    corpo: dict[str, Any] = {"valor": "10.00", "descricao": "Servico de teste"}
    corpo.update(extra)
    return {"idempotency_key": chave, **corpo}


async def emitir(cliente, tenant: dict[str, Any], chave: str, **extra: Any):
    return await cliente.post(
        "/v1/emissoes", json=corpo_emissao(chave, **extra), headers=cabecalho(tenant)
    )


@pytest.fixture
async def pronto(cliente, app_teste):
    """Tenant com configuração fiscal, certificado e dublê da SEFIN ligado."""
    app_teste.dependency_overrides[get_settings] = lambda: Settings(
        environment="test", nfse_adapter="mock"
    )
    tenant = await criar_tenant(cliente, "ramos-emissao")
    await configurar(cliente, tenant)
    await enviar_certificado(cliente, tenant)
    yield {"tenant": tenant, "cabecalho": cabecalho(tenant)}
    app_teste.dependency_overrides.clear()


@pytest.fixture
async def emitida(cliente, pronto) -> dict[str, Any]:
    """Uma emissão autorizada, base para DANFSe, representação, eventos e cancelamento."""
    resposta = await emitir(cliente, pronto["tenant"], "ramos-0001")
    assert resposta.status_code == 201, resposta.text
    return {**pronto, "emissao": resposta.json()}


class ResultadoFalso:
    """Resultado de `session.execute` reduzido ao que o código consome."""

    def __init__(self, itens: list[Any] | Any = None) -> None:
        self._itens = itens if isinstance(itens, list) else ([itens] if itens is not None else [])

    def scalar_one_or_none(self):
        return self._itens[0] if self._itens else None

    def scalar_one(self):
        assert self._itens, "scalar_one sem linha"
        return self._itens[0]

    def scalars(self) -> ResultadoFalso:
        return self

    def first(self):
        return self._itens[0] if self._itens else None

    def all(self) -> list[Any]:
        return list(self._itens)


class SessaoFalsa:
    """Sessão dublê: cada `execute` consome um resultado da fila, na ordem do código.

    Ordem é o que importa: o handler faz várias consultas, e devolver sempre o mesmo
    resultado esconderia justamente o ramo testado.
    """

    def __init__(self, *resultados: Any) -> None:
        self._fila = list(resultados)
        self.adicionados: list[Any] = []
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0
        self.refreshes: list[Any] = []
        self.falhar_flush: BaseException | None = None
        self.executadas: list[Any] = []

    async def execute(self, consulta: Any, *_a: Any, **_k: Any) -> ResultadoFalso:
        self.executadas.append(consulta)
        if self._fila:
            proximo = self._fila.pop(0)
            return proximo if isinstance(proximo, ResultadoFalso) else ResultadoFalso(proximo)
        return ResultadoFalso()

    def add(self, objeto: Any) -> None:
        self.adicionados.append(objeto)

    async def flush(self) -> None:
        if self.falhar_flush is not None:
            erro, self.falhar_flush = self.falhar_flush, None
            raise erro
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, objeto: Any) -> None:
        self.refreshes.append(objeto)


def settings_mock() -> Settings:
    return Settings(environment="test", nfse_adapter="mock")


def tenant_falso(tenant_id: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=tenant_id or uuid.uuid4())


def fatura(**extra: Any) -> Invoice:
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "idempotency_key": "chave-para-teste",
        "status": StatusFatura.PENDENTE,
        "tipo_documento": TipoDocumento.NFSE,
        "valor_servico": "10.00",
        "descricao_servico": "servico",
        "competencia": "2026-11",
        "tomador_documento": "11144477735",
        "tomador_nome": "Tomador Exemplo",
    }
    base.update(extra)
    return Invoice(**base)


def documento_da(invoice: Invoice, **extra: Any) -> FiscalDocument:
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "tenant_id": invoice.tenant_id,
        "invoice_id": invoice.id,
        "tipo_documento": TipoDocumento.NFSE,
        "ambiente": AmbienteFiscal.HOMOLOGACAO,
        "chave": CHAVE_MOCK,
        "xml_autorizado": NFSE_XML,
        "emitido_em": datetime.now(UTC),
    }
    base.update(extra)
    return FiscalDocument(**base)


def entrada(**extra: Any) -> EmissaoIn:
    base: dict[str, Any] = {
        "valor": "10.00",
        "descricao": "Servico de teste",
        "municipio_ibge": MUNICIPIO,
    }
    base.update(extra)
    return EmissaoIn(**base)


# ---------------------------------------------------------------------------
# HTTP: DANFSe
# ---------------------------------------------------------------------------
class TestDanfse:
    async def test_pdf_do_documento_autorizado(self, cliente, emitida) -> None:
        evento = emitida["emissao"]

        resposta = await cliente.get(
            f"/v1/emissoes/{evento['invoice_id']}/danfse", headers=emitida["cabecalho"]
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.headers["content-type"] == "application/pdf"
        assert resposta.content.startswith(b"%PDF")
        assert evento["chave"] in resposta.headers["content-disposition"]

    async def test_emissao_inexistente_da_404(self, cliente, emitida) -> None:
        resposta = await cliente.get(
            f"/v1/emissoes/{uuid.uuid4()}/danfse", headers=emitida["cabecalho"]
        )

        assert resposta.status_code == 404
        assert resposta.json()["detail"] == "emissão não encontrada"

    async def test_fatura_sem_documento_da_422(self, cliente, pronto, monkeypatch) -> None:
        """Emissão que falha na SEFIN deixa fatura sem documento: não há o que representar."""

        def falhar(self, dps_assinada: bytes) -> RespostaEmissao:
            raise ErroSefin(TipoErroFiscal.INDISPONIVEL, "SEFIN fora do ar")

        monkeypatch.setattr(SefinMockAdapter, "emitir", falhar)

        criada = await emitir(cliente, pronto["tenant"], "danfse-sem-doc")
        assert criada.status_code == 502, criada.text
        invoice_id = (await cliente.get("/v1/emissoes", headers=pronto["cabecalho"])).json()[0][
            "invoice_id"
        ]

        resposta = await cliente.get(
            f"/v1/emissoes/{invoice_id}/danfse", headers=pronto["cabecalho"]
        )

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == "emissão sem documento fiscal"

    async def test_documento_sem_xml_autorizado_da_422(self, cliente, sessao_db, pronto) -> None:
        """Documento existe, mas sem XML: o DANFSe representa nota autorizada, não rascunho."""
        fatura_sem_xml = fatura(
            tenant_id=uuid.UUID(pronto["tenant"]["id"]), idempotency_key="sem-xml-0001"
        )
        sessao_db.add(fatura_sem_xml)
        await sessao_db.flush()
        sessao_db.add(documento_da(fatura_sem_xml, chave=None, xml_autorizado=None))
        await sessao_db.commit()

        resposta = await cliente.get(
            f"/v1/emissoes/{fatura_sem_xml.id}/danfse", headers=pronto["cabecalho"]
        )

        assert resposta.status_code == 422
        assert "XML autorizado" in resposta.json()["detail"]


# ---------------------------------------------------------------------------
# HTTP: representação impressa
# ---------------------------------------------------------------------------
class TestRepresentacao:
    async def test_danfse_da_nfse(self, cliente, emitida) -> None:
        resposta = await cliente.get(
            f"/v1/emissoes/{emitida['emissao']['invoice_id']}/representacao?formato=danfse",
            headers=emitida["cabecalho"],
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.content.startswith(b"%PDF")
        assert "danfse-" in resposta.headers["content-disposition"]

    async def test_formato_inexistente_lista_o_que_existe(self, cliente, emitida) -> None:
        """Pedir `danfe_simplificado` para uma NFS-e é erro de formato, não PDF vazio."""
        resposta = await cliente.get(
            f"/v1/emissoes/{emitida['emissao']['invoice_id']}/representacao",
            headers=emitida["cabecalho"],
        )

        assert resposta.status_code == 422
        detalhe = str(resposta.json()["detail"])
        assert "danfse" in detalhe, "o erro deve listar as representações registradas"

    async def test_emissao_inexistente_da_404(self, cliente, emitida) -> None:
        resposta = await cliente.get(
            f"/v1/emissoes/{uuid.uuid4()}/representacao", headers=emitida["cabecalho"]
        )

        assert resposta.status_code == 404
        assert resposta.json()["detail"] == "emissão não encontrada"

    async def test_sem_xml_autorizado_da_422(self, cliente, sessao_db, pronto) -> None:
        fatura_sem_xml = fatura(
            tenant_id=uuid.UUID(pronto["tenant"]["id"]), idempotency_key="repr-sem-xml"
        )
        sessao_db.add(fatura_sem_xml)
        await sessao_db.flush()
        sessao_db.add(documento_da(fatura_sem_xml, chave=None, xml_autorizado=None))
        await sessao_db.commit()

        resposta = await cliente.get(
            f"/v1/emissoes/{fatura_sem_xml.id}/representacao", headers=pronto["cabecalho"]
        )

        assert resposta.status_code == 422
        assert "sem XML autorizado" in resposta.json()["detail"]


# ---------------------------------------------------------------------------
# HTTP: catálogos
# ---------------------------------------------------------------------------
class TestCatalogos:
    async def test_tipos_de_evento_trazem_campos_do_leiaute(self, cliente, pronto) -> None:
        resposta = await cliente.get("/v1/emissoes/eventos/tipos", headers=pronto["cabecalho"])

        assert resposta.status_code == 200
        tipos = resposta.json()
        assert len(tipos) == 16
        codigos = {tipo["codigo"] for tipo in tipos}
        assert "101101" in codigos, "cancelamento é um tipo do catálogo, com rota própria"
        confirmacao = next(t for t in tipos if t["codigo"] == "202201")
        assert confirmacao["operavel_pelo_contribuinte"] is True
        assert confirmacao["descricao"], "xDesc vem pronta do catálogo"
        assert [t["codigo"] for t in tipos] == sorted(t["codigo"] for t in tipos)

    async def test_motivos_de_cancelamento(self, cliente, pronto) -> None:
        resposta = await cliente.get(
            "/v1/emissoes/cancelamento/motivos", headers=pronto["cabecalho"]
        )

        assert resposta.status_code == 200
        motivos = resposta.json()
        assert set(motivos) == {"1", "2", "9"}
        assert all(texto for texto in motivos.values())


# ---------------------------------------------------------------------------
# HTTP: cancelamento
# ---------------------------------------------------------------------------
class TestCancelamento:
    async def test_cancela_nota_autorizada(self, cliente, emitida) -> None:
        invoice_id = emitida["emissao"]["invoice_id"]

        resposta = await cliente.post(
            f"/v1/emissoes/{invoice_id}/cancelamento",
            json={"c_motivo": "1", "x_motivo": MOTIVO},
            headers=emitida["cabecalho"],
        )

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["status"] == StatusFatura.CANCELADA.value
        assert corpo["chave"] == emitida["emissao"]["chave"]
        assert corpo["data_processamento"]
        assert "1" in corpo["motivos"]

    async def test_inexistente_da_404(self, cliente, emitida) -> None:
        resposta = await cliente.post(
            f"/v1/emissoes/{uuid.uuid4()}/cancelamento",
            json={"c_motivo": "1", "x_motivo": MOTIVO},
            headers=emitida["cabecalho"],
        )

        assert resposta.status_code == 404
        assert resposta.json()["detail"] == "emissão não encontrada"

    async def test_nota_nao_autorizada_da_409(self, cliente, pronto, monkeypatch) -> None:
        def falhar(self, dps_assinada: bytes) -> RespostaEmissao:
            raise ErroSefin(TipoErroFiscal.INDISPONIVEL, "SEFIN fora do ar")

        monkeypatch.setattr(SefinMockAdapter, "emitir", falhar)
        criada = await emitir(cliente, pronto["tenant"], "cancelar-sem-nota")
        assert criada.status_code == 502, criada.text

        listagem = await cliente.get("/v1/emissoes", headers=pronto["cabecalho"])
        invoice_id = listagem.json()[0]["invoice_id"]

        resposta = await cliente.post(
            f"/v1/emissoes/{invoice_id}/cancelamento",
            json={"c_motivo": "1", "x_motivo": MOTIVO},
            headers=pronto["cabecalho"],
        )

        assert resposta.status_code == 409, resposta.text
        assert "documento autorizado" in resposta.json()["detail"].lower()

    async def test_motivo_curto_da_422(self, cliente, emitida) -> None:
        resposta = await cliente.post(
            f"/v1/emissoes/{emitida['emissao']['invoice_id']}/cancelamento",
            json={"c_motivo": "1", "x_motivo": "curto"},
            headers=emitida["cabecalho"],
        )

        assert resposta.status_code == 422


# ---------------------------------------------------------------------------
# HTTP: ramos do POST /v1/emissoes
# ---------------------------------------------------------------------------
class TestEmissaoHttp:
    async def test_reenvio_de_fatura_com_erro_devolve_estado(
        self, cliente, pronto, monkeypatch
    ) -> None:
        """Fatura existe e não está autorizada: devolve o estado, não reprocessa."""

        def falhar(self, dps_assinada: bytes) -> RespostaEmissao:
            raise ErroSefin(TipoErroFiscal.INDISPONIVEL, "SEFIN fora do ar")

        monkeypatch.setattr(SefinMockAdapter, "emitir", falhar)
        primeira = await emitir(cliente, pronto["tenant"], "estado-nao-autorizado")
        assert primeira.status_code == 502, primeira.text

        segunda = await emitir(cliente, pronto["tenant"], "estado-nao-autorizado")

        # 200, não 201: nada foi criado nesta chamada. Antes o ramo "existe mas não está
        # autorizada" herdava o 201 da rota e anunciava criação que não houve (§101).
        assert segunda.status_code == 200, segunda.text
        corpo = segunda.json()
        assert corpo["ja_existia"] is True
        assert corpo["status"] == StatusFatura.ERRO.value
        assert corpo["chave"] is None
        assert corpo["documento"] is None

    async def test_erro_da_sefin_vira_502_com_detalhe_estruturado(
        self, cliente, pronto, monkeypatch
    ) -> None:
        def falhar(self, dps_assinada: bytes) -> RespostaEmissao:
            raise ErroSefin(TipoErroFiscal.INDISPONIVEL, "SEFIN fora do ar")

        monkeypatch.setattr(SefinMockAdapter, "emitir", falhar)

        resposta = await emitir(cliente, pronto["tenant"], "sefin-502")

        assert resposta.status_code == 502, resposta.text
        assert resposta.headers["content-type"].startswith("application/problem+json")
        corpo = resposta.json()
        assert corpo["retryable"] is True
        # `HTTPException(detail=exc.as_dict())` chega ao cliente como **string**: o handler
        # RFC 7807 aplica `str()` em `detail` não-textual. O conteúdo está lá, mas não é JSON.
        detalhe = corpo["detail"]
        assert "SEFIN fora do ar" in detalhe
        assert "pode_ter_sido_processada" in detalhe

    async def test_listagem_aceita_fatura_sem_documento(self, cliente, pronto, monkeypatch) -> None:
        def falhar(self, dps_assinada: bytes) -> RespostaEmissao:
            raise ErroSefin(TipoErroFiscal.INDISPONIVEL, "SEFIN fora do ar")

        monkeypatch.setattr(SefinMockAdapter, "emitir", falhar)
        await emitir(cliente, pronto["tenant"], "listagem-sem-doc")

        listagem = await cliente.get("/v1/emissoes", headers=pronto["cabecalho"])

        assert listagem.status_code == 200
        itens = listagem.json()
        assert len(itens) == 1
        assert itens[0]["documento"] is None
        assert itens[0]["chave"] is None
        assert itens[0]["erro"]

    async def test_consulta_de_fatura_sem_documento(self, cliente, pronto, monkeypatch) -> None:
        def falhar(self, dps_assinada: bytes) -> RespostaEmissao:
            raise ErroSefin(TipoErroFiscal.INDISPONIVEL, "SEFIN fora do ar")

        monkeypatch.setattr(SefinMockAdapter, "emitir", falhar)
        criada = await emitir(cliente, pronto["tenant"], "consulta-sem-doc")
        assert criada.status_code == 502
        invoice_id = (await cliente.get("/v1/emissoes", headers=pronto["cabecalho"])).json()[0][
            "invoice_id"
        ]

        consulta = await cliente.get(f"/v1/emissoes/{invoice_id}", headers=pronto["cabecalho"])

        assert consulta.status_code == 200
        assert consulta.json()["xml_autorizado"] is None
        assert consulta.json()["documento"] is None

    async def test_configuracao_ambigua_exige_municipio(self, cliente, pronto) -> None:
        pessoa = pronto["tenant"]
        await configurar(cliente, pessoa, municipio=MUNICIPIO_B, uf="SP")

        ambiguo = await emitir(cliente, pessoa, "ambigua-0001")
        assert ambiguo.status_code == 422, ambiguo.text
        assert "municipio_ibge" in ambiguo.json()["detail"]
        assert MUNICIPIO in ambiguo.json()["detail"]
        assert MUNICIPIO_B in ambiguo.json()["detail"]

        resolvido = await emitir(cliente, pessoa, "ambigua-0002", municipio_ibge=MUNICIPIO)
        assert resolvido.status_code == 201, resolvido.text

    async def test_rota_bloqueada_em_producao_explica_a_pendencia(self, cliente, pronto) -> None:
        """Em produção, parâmetro municipal não confirmado não pode ser presumido (§77)."""
        pessoa = pronto["tenant"]
        await configurar(
            cliente,
            pessoa,
            ambiente="producao",
            aderente_emissor_nacional=False,
            simples_nacional=False,
        )

        resposta = await emitir(cliente, pessoa, "rota-bloqueada", ambiente="producao")

        assert resposta.status_code == 422, resposta.text
        detalhe = resposta.json()["detail"]
        assert "Pendência:" in detalhe
        assert "aderente_confirmado_em" in detalhe
        assert "não foi conferido" in detalhe

    async def test_fatura_nao_autorizada_nao_e_reprocessada(
        self, cliente, pronto, sessao_db, monkeypatch
    ) -> None:
        """O reenvio devolve 200 com o estado atual e não tenta emitir de novo."""

        def falhar(self, dps_assinada: bytes) -> RespostaEmissao:
            raise ErroSefin(TipoErroFiscal.INDISPONIVEL, "SEFIN fora do ar")

        monkeypatch.setattr(SefinMockAdapter, "emitir", falhar)
        await emitir(cliente, pronto["tenant"], "nao-reprocessa")

        chamadas = 0

        def contar_e_falhar(self, dps_assinada: bytes) -> RespostaEmissao:
            nonlocal chamadas
            chamadas += 1
            raise ErroSefin(TipoErroFiscal.INDISPONIVEL, "SEFIN fora do ar")

        monkeypatch.setattr(SefinMockAdapter, "emitir", contar_e_falhar)
        segunda = await emitir(cliente, pronto["tenant"], "nao-reprocessa")

        assert segunda.status_code == 200, segunda.text
        assert segunda.json()["ja_existia"] is True
        assert chamadas == 0, "fatura não autorizada não deve ser transmitida de novo"


# ---------------------------------------------------------------------------
# Unitário: mapeamento de erro do handler `emitir`
# ---------------------------------------------------------------------------
class TestMapeamentoDeErros:
    """O handler é chamado direto: o que se testa aqui é a tradução exceção → HTTP."""

    async def test_fatura_autorizada_ja_existente_devolve_200(self) -> None:
        dados = entrada(idempotency_key="idem-00000001")
        existente = fatura(status=StatusFatura.AUTORIZADA, payload=dados.model_dump(mode="json"))
        doc = documento_da(existente)
        sessao = SessaoFalsa(None, existente, doc)

        resposta = await emissoes.emitir(
            dados,
            idempotency_key="idem-00000001",
            tenant=tenant_falso(existente.tenant_id),
            db=sessao,
            settings=settings_mock(),
        )

        assert resposta.status_code == 200
        corpo = resposta.body
        assert b'"ja_existia":true' in corpo.replace(b" ", b"")
        assert CHAVE_MOCK.encode() in corpo
        assert sessao.commits == 0, "reenvio não abre transação nova"

    async def test_fatura_existente_sem_autorizacao_devolve_estado(self) -> None:
        dados = entrada(idempotency_key="idem-00000002")
        existente = fatura(
            status=StatusFatura.REJEITADA,
            payload=dados.model_dump(mode="json"),
            erro="rejeitada pela SEFIN",
        )
        sessao = SessaoFalsa(None, existente, None)

        saida = await emissoes.emitir(
            dados,
            idempotency_key="idem-00000002",
            tenant=tenant_falso(existente.tenant_id),
            db=sessao,
            settings=settings_mock(),
        )

        # Estado atual é 200 com corpo JSON: nada foi criado nesta chamada (§101).
        assert saida.status_code == 200
        corpo = json.loads(saida.body)
        assert corpo["ja_existia"] is True
        assert corpo["status"] == StatusFatura.REJEITADA.value
        assert corpo["chave"] is None
        assert corpo["erro"] == "rejeitada pela SEFIN"

    async def test_payload_divergente_da_409(self) -> None:
        existente = fatura(status=StatusFatura.AUTORIZADA, payload={"valor": "99.00"})
        sessao = SessaoFalsa(None, existente)

        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.emitir(
                entrada(idempotency_key="idem-00000003"),
                idempotency_key="idem-00000003",
                tenant=tenant_falso(existente.tenant_id),
                db=sessao,
                settings=settings_mock(),
            )

        assert erro.value.status_code == 409
        assert "corpo diferente" in str(erro.value.detail)

    async def test_corrida_perdida_recupera_a_fatura_existente(self) -> None:
        """A constraint dispara: o handler recupera a fatura que a outra transação criou."""
        dados = entrada(idempotency_key="idem-00000004")
        existente = fatura(status=StatusFatura.AUTORIZADA, payload=dados.model_dump(mode="json"))
        doc = documento_da(existente)
        # Ordem: trava de idempotência, primeira busca (nada), busca após o conflito, documento.
        sessao = SessaoFalsa(None, None, existente, doc)
        sessao.falhar_flush = IntegrityError("insert", {}, Exception("uq"))

        saida = await emissoes.emitir(
            dados,
            idempotency_key="idem-00000004",
            tenant=tenant_falso(existente.tenant_id),
            db=sessao,
            settings=settings_mock(),
        )

        assert sessao.rollbacks == 1, "transação perdedora precisa ser abandonada"
        assert saida.status_code == 200
        corpo = json.loads(saida.body)
        assert corpo["ja_existia"] is True
        assert corpo["chave"] == CHAVE_MOCK

    async def test_corrida_sem_fatura_visivel_da_409(self) -> None:
        sessao = SessaoFalsa(None, None)
        sessao.falhar_flush = IntegrityError("insert", {}, Exception("uq"))

        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.emitir(
                entrada(idempotency_key="idem-00000005"),
                idempotency_key="idem-00000005",
                tenant=tenant_falso(),
                db=sessao,
                settings=settings_mock(),
            )

        assert erro.value.status_code == 409
        assert "conflito de idempotência" in str(erro.value.detail)

    @pytest.mark.parametrize(
        ("excecao", "status_esperado", "trecho", "commits", "rollbacks"),
        [
            (
                emissao_service.ConfiguracaoFiscalAmbigua("escolha o município"),
                422,
                "município",
                0,
                1,
            ),
            (
                emissao_service.ConfiguracaoFiscalAusente("cadastre a configuração"),
                422,
                "configuração",
                1,
                0,
            ),
            (
                emissao_service.CertificadoAusente("sem certificado A1 ativo"),
                422,
                "certificado",
                1,
                0,
            ),
            (emissao_service.ErroDeEmissao("falha local"), 422, "falha local", 1, 0),
        ],
    )
    async def test_erros_locais_viram_422(
        self,
        monkeypatch,
        excecao: Exception,
        status_esperado: int,
        trecho: str,
        commits: int,
        rollbacks: int,
    ) -> None:
        async def levantar(*_a: Any, **_k: Any):
            raise excecao

        monkeypatch.setattr(emissoes.emissao_service, "emitir", levantar)
        sessao = SessaoFalsa()

        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.emitir(
                entrada(idempotency_key="idem-00000006"),
                idempotency_key="idem-00000006",
                tenant=tenant_falso(),
                db=sessao,
                settings=settings_mock(),
            )

        assert erro.value.status_code == status_esperado
        assert trecho in str(erro.value.detail)
        # Ambiguação é estado a corrigir: descarta a transação. Os demais preservam o evento
        # de erro que o serviço registrou antes de levantar.
        assert sessao.commits == commits
        assert sessao.rollbacks == rollbacks

    async def test_rota_nao_permitida_leva_a_pendencia_ao_cliente(self, monkeypatch) -> None:
        async def levantar(*_a: Any, **_k: Any):
            raise emissao_service.RotaNaoPermitida(
                "município não aderente", pendencia="homologar o transporte municipal"
            )

        monkeypatch.setattr(emissoes.emissao_service, "emitir", levantar)

        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.emitir(
                entrada(idempotency_key="idem-00000007"),
                idempotency_key="idem-00000007",
                tenant=tenant_falso(),
                db=SessaoFalsa(),
                settings=settings_mock(),
            )

        assert erro.value.status_code == 422
        detalhe = str(erro.value.detail)
        assert "município não aderente" in detalhe
        assert "Pendência: homologar o transporte municipal" in detalhe

    async def test_certificado_ambiguo_da_409(self, monkeypatch) -> None:
        from app.certificates.service import CertificadoAmbiguo

        async def levantar(*_a: Any, **_k: Any):
            raise CertificadoAmbiguo("há mais de um certificado ativo")

        monkeypatch.setattr(emissoes.emissao_service, "emitir", levantar)
        sessao = SessaoFalsa()

        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.emitir(
                entrada(idempotency_key="idem-00000008"),
                idempotency_key="idem-00000008",
                tenant=tenant_falso(),
                db=sessao,
                settings=settings_mock(),
            )

        assert erro.value.status_code == 409
        assert sessao.rollbacks == 1, "ambiguidade exige resolver estado, não preservar meio-termo"

    async def test_erro_sefin_vira_502_com_dicionario(self, monkeypatch) -> None:
        async def levantar(*_a: Any, **_k: Any):
            raise ErroSefin(TipoErroFiscal.REJEICAO, "E0429 aliquota invalida")

        monkeypatch.setattr(emissoes.emissao_service, "emitir", levantar)
        sessao = SessaoFalsa()

        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.emitir(
                entrada(idempotency_key="idem-00000009"),
                idempotency_key="idem-00000009",
                tenant=tenant_falso(),
                db=sessao,
                settings=settings_mock(),
            )

        assert erro.value.status_code == 502
        assert erro.value.detail["tipo"] == TipoErroFiscal.REJEICAO.value

    async def test_emissao_bem_sucedida_devolve_201(self, monkeypatch) -> None:
        invoice_criada: dict[str, Any] = {}

        async def emitir_dublado(sessao, tenant, invoice, **_k: Any):
            # O `id` real vem do INSERT; a sessão dublê não fala com o banco, então o
            # identificador é atribuído aqui para que a serialização de saída funcione.
            invoice.id = uuid.uuid4()
            invoice.status = StatusFatura.AUTORIZADA
            invoice_criada["invoice"] = invoice
            return documento_da(invoice)

        monkeypatch.setattr(emissoes.emissao_service, "emitir", emitir_dublado)
        sessao = SessaoFalsa()

        saida = await emissoes.emitir(
            entrada(idempotency_key="idem-00000010"),
            idempotency_key="idem-00000010",
            tenant=tenant_falso(),
            db=sessao,
            settings=settings_mock(),
        )

        assert saida.ja_existia is False
        assert saida.chave == CHAVE_MOCK
        assert saida.documento is not None
        assert saida.documento.tem_xml_autorizado is True
        assert sessao.commits == 1
        assert len(sessao.refreshes) == 2, "fatura e documento são relidos após o commit"
        assert invoice_criada["invoice"].competencia, "competência default é o mês corrente"


# ---------------------------------------------------------------------------
# Unitário: sessão dublê só para caminhos que a API não alcança
# ---------------------------------------------------------------------------
class TestConsultasDoHandler:
    async def test_busca_por_idempotencia_devolve_none(self) -> None:
        assert await emissoes._buscar_por_idempotencia(SessaoFalsa(), uuid.uuid4(), "x") is None

    async def test_busca_por_idempotencia_devolve_fatura(self) -> None:
        existente = fatura()
        achada = await emissoes._buscar_por_idempotencia(
            SessaoFalsa(existente), existente.tenant_id, existente.idempotency_key
        )

        assert achada is existente

    async def test_documento_da_fatura_devolve_none(self) -> None:
        assert await emissoes._documento_da_fatura(SessaoFalsa(), fatura()) is None

    async def test_documento_da_fatura_devolve_documento(self) -> None:
        invoice = fatura()
        doc = documento_da(invoice)

        achado = await emissoes._documento_da_fatura(SessaoFalsa(doc), invoice)

        assert achado is doc

    async def test_listagem_sem_faturas(self, cliente, pronto) -> None:
        resposta = await cliente.get("/v1/emissoes", headers=pronto["cabecalho"])

        assert resposta.status_code == 200
        assert resposta.json() == []


class TestConsultaEListagem:
    async def test_consulta_com_documento_devolve_xml(self) -> None:
        invoice = fatura(status=StatusFatura.AUTORIZADA)
        doc = documento_da(invoice)

        saida = await emissoes.consultar_emissao(
            invoice.id, tenant=tenant_falso(invoice.tenant_id), db=SessaoFalsa(invoice, doc)
        )

        assert saida.xml_autorizado == NFSE_XML
        assert saida.documento is not None
        assert saida.documento.chave == CHAVE_MOCK
        assert saida.chave == CHAVE_MOCK

    async def test_consulta_de_emissao_inexistente_da_404(self) -> None:
        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.consultar_emissao(
                uuid.uuid4(), tenant=tenant_falso(), db=SessaoFalsa(None)
            )

        assert erro.value.status_code == 404

    async def test_listagem_devolve_uma_entrada_por_fatura(self) -> None:
        primeira = fatura(idempotency_key="lista-0001")
        segunda = fatura(idempotency_key="lista-0002", status=StatusFatura.REJEITADA)
        sessao = SessaoFalsa([primeira, segunda], documento_da(primeira), None)

        saida = await emissoes.listar_emissoes(
            limite=50, deslocamento=0, tenant=tenant_falso(primeira.tenant_id), db=sessao
        )

        assert [item.idempotency_key for item in saida] == ["lista-0001", "lista-0002"]
        assert saida[0].documento is not None
        assert saida[1].documento is None, "fatura rejeitada não tem documento para mostrar"


class TestDanfseHandler:
    """Mapeamento do handler, sem HTTP: os mesmos ramos que a rota expõe."""

    async def test_pdf_gerado(self, monkeypatch) -> None:
        invoice = fatura(status=StatusFatura.AUTORIZADA)
        doc = documento_da(invoice)
        monkeypatch.setattr(emissoes, "gerar_pdf_do_documento", lambda _doc: b"%PDF-1.4 fake")

        resposta = await emissoes.baixar_danfse(
            invoice.id, tenant=tenant_falso(invoice.tenant_id), db=SessaoFalsa(invoice, doc)
        )

        assert resposta.media_type == "application/pdf"
        assert resposta.body == b"%PDF-1.4 fake"
        assert CHAVE_MOCK in resposta.headers["content-disposition"]

    async def test_emissao_inexistente_da_404(self) -> None:
        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.baixar_danfse(uuid.uuid4(), tenant=tenant_falso(), db=SessaoFalsa(None))

        assert erro.value.status_code == 404

    async def test_sem_documento_da_422(self) -> None:
        invoice = fatura()

        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.baixar_danfse(
                invoice.id, tenant=tenant_falso(invoice.tenant_id), db=SessaoFalsa(invoice, None)
            )

        assert erro.value.status_code == 422

    async def test_documento_sem_xml_da_422(self, monkeypatch) -> None:
        from app.danfse.service import ErroDanfse

        invoice = fatura(status=StatusFatura.AUTORIZADA)
        doc = documento_da(invoice, xml_autorizado=None)

        def falhar(_doc):
            raise ErroDanfse("documento sem XML autorizado")

        monkeypatch.setattr(emissoes, "gerar_pdf_do_documento", falhar)

        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.baixar_danfse(
                invoice.id, tenant=tenant_falso(invoice.tenant_id), db=SessaoFalsa(invoice, doc)
            )

        assert erro.value.status_code == 422
        assert "XML autorizado" in str(erro.value.detail)


class TestRepresentacaoHandler:
    async def test_pdf_gerado(self, monkeypatch) -> None:
        invoice = fatura(status=StatusFatura.AUTORIZADA)
        doc = documento_da(invoice)
        chamadas: list[tuple[Any, ...]] = []

        def gerar(tipo: str, xml: bytes, *, formato: str) -> bytes:
            chamadas.append((tipo, xml, formato))
            return b"%PDF-1.4 repr"

        monkeypatch.setattr(emissoes, "gerar_representacao", gerar)

        resposta = await emissoes.baixar_representacao(
            invoice.id,
            formato="danfse",
            tenant=tenant_falso(invoice.tenant_id),
            db=SessaoFalsa(invoice, doc),
        )

        assert resposta.body == b"%PDF-1.4 repr"
        assert chamadas == [(TipoDocumento.NFSE.value, NFSE_XML.encode("utf-8"), "danfse")]
        assert resposta.headers["content-disposition"].startswith('inline; filename="danfse-')

    async def test_emissao_inexistente_da_404(self) -> None:
        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.baixar_representacao(
                uuid.uuid4(), formato="danfse", tenant=tenant_falso(), db=SessaoFalsa(None)
            )

        assert erro.value.status_code == 404

    async def test_sem_xml_autorizado_da_422(self) -> None:
        invoice = fatura()
        doc = documento_da(invoice, chave=None, xml_autorizado=None)

        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.baixar_representacao(
                invoice.id,
                formato="danfse",
                tenant=tenant_falso(invoice.tenant_id),
                db=SessaoFalsa(invoice, doc),
            )

        assert erro.value.status_code == 422
        assert "sem XML autorizado" in str(erro.value.detail)

    async def test_formato_invalido_da_422(self, monkeypatch) -> None:
        from app.danfe import ErroRepresentacao

        invoice = fatura(status=StatusFatura.AUTORIZADA)
        doc = documento_da(invoice)

        def falhar(*_a: Any, **_k: Any):
            raise ErroRepresentacao("formato 'x' não existe; disponíveis: danfse")

        monkeypatch.setattr(emissoes, "gerar_representacao", falhar)

        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.baixar_representacao(
                invoice.id,
                formato="x",
                tenant=tenant_falso(invoice.tenant_id),
                db=SessaoFalsa(invoice, doc),
            )

        assert erro.value.status_code == 422
        assert "danfse" in str(erro.value.detail)


class TestEventosHandlers:
    async def test_disponiveis_sem_oficio(self) -> None:
        corpo = await emissoes.eventos_disponiveis(incluir_oficio=False)

        assert "101101" not in corpo["tipos"]
        assert "202201" in corpo["tipos"]
        assert "incluir_oficio=true" in corpo["observacao"]

    async def test_disponiveis_com_oficio(self) -> None:
        corpo = await emissoes.eventos_disponiveis(incluir_oficio=True)

        assert "305101" in corpo["tipos"]

    async def test_registro_bem_sucedido(self, monkeypatch) -> None:
        invoice = fatura(status=StatusFatura.AUTORIZADA)
        capturado: dict[str, Any] = {}

        async def registrar(_sessao, _tenant, _invoice, *, codigo, campos, **_k):
            capturado.update({"codigo": codigo, "campos": campos})
            return SimpleNamespace(data_processamento="2026-11-25T12:00:00-03:00")

        monkeypatch.setattr(emissoes.eventos_service, "registrar", registrar)
        sessao = SessaoFalsa(invoice)

        saida = await emissoes.registrar_evento(
            invoice.id,
            emissoes.EventoIn(codigo="202201", campos={}),
            tenant=tenant_falso(invoice.tenant_id),
            db=sessao,
            settings=settings_mock(),
        )

        assert saida.codigo == "202201"
        assert saida.status == StatusFatura.AUTORIZADA.value
        assert saida.data_processamento == "2026-11-25T12:00:00-03:00"
        assert capturado == {"codigo": "202201", "campos": {}}
        assert sessao.commits == 1

    async def test_emissao_inexistente_da_404(self) -> None:
        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.registrar_evento(
                uuid.uuid4(),
                emissoes.EventoIn(codigo="202201"),
                tenant=tenant_falso(),
                db=SessaoFalsa(None),
                settings=settings_mock(),
            )

        assert erro.value.status_code == 404

    @pytest.mark.parametrize(
        ("excecao", "status_esperado"),
        [
            (emissoes.eventos_service.TipoReservado("cancelamento tem rota própria"), 422),
            (emissoes.eventos_service.EventoNaoAplicavel("tipo de ofício"), 422),
            (
                emissoes.ErroDeEventoCatalogo("999999 não existe no catálogo"),
                422,
            ),
            (emissoes.eventos_service.ErroDeEvento("evento fora de ordem"), 409),
        ],
    )
    async def test_erros_do_catalogo(
        self, monkeypatch, excecao: Exception, status_esperado: int
    ) -> None:
        invoice = fatura(status=StatusFatura.AUTORIZADA)

        async def levantar(*_a: Any, **_k: Any):
            raise excecao

        monkeypatch.setattr(emissoes.eventos_service, "registrar", levantar)
        sessao = SessaoFalsa(invoice)

        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.registrar_evento(
                invoice.id,
                emissoes.EventoIn(codigo="202201"),
                tenant=tenant_falso(invoice.tenant_id),
                db=sessao,
                settings=settings_mock(),
            )

        assert erro.value.status_code == status_esperado
        assert str(excecao) in str(erro.value.detail)
        assert sessao.rollbacks == 1

    async def test_erro_sefin_no_evento_da_502(self, monkeypatch) -> None:
        invoice = fatura(status=StatusFatura.AUTORIZADA)

        async def levantar(*_a: Any, **_k: Any):
            raise ErroSefin(TipoErroFiscal.INDISPONIVEL, "SEFIN fora do ar")

        monkeypatch.setattr(emissoes.eventos_service, "registrar", levantar)
        sessao = SessaoFalsa(invoice)

        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.registrar_evento(
                invoice.id,
                emissoes.EventoIn(codigo="202201"),
                tenant=tenant_falso(invoice.tenant_id),
                db=sessao,
                settings=settings_mock(),
            )

        assert erro.value.status_code == 502
        assert sessao.commits == 1, "resposta da SEFIN precisa ser preservada"


class TestCancelamentoHandler:
    async def test_cancelamento_bem_sucedido(self, monkeypatch) -> None:
        invoice = fatura(status=StatusFatura.AUTORIZADA)
        doc = documento_da(invoice)

        async def cancelar(_sessao, _tenant, _invoice, *, c_motivo, x_motivo, **_k):
            _invoice.status = StatusFatura.CANCELADA
            return SimpleNamespace(data_processamento="2026-11-25T12:00:00-03:00")

        monkeypatch.setattr(emissoes.cancelamento_service, "cancelar", cancelar)
        sessao = SessaoFalsa(invoice, doc)

        saida = await emissoes.cancelar_emissao(
            invoice.id,
            emissoes.CancelamentoIn(c_motivo="1", x_motivo=MOTIVO),
            tenant=tenant_falso(invoice.tenant_id),
            db=sessao,
            settings=settings_mock(),
        )

        assert saida.status == StatusFatura.CANCELADA.value
        assert saida.chave == CHAVE_MOCK
        assert saida.data_processamento == "2026-11-25T12:00:00-03:00"
        assert saida.motivos
        assert sessao.commits == 1

    async def test_emissao_inexistente_da_404(self) -> None:
        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.cancelar_emissao(
                uuid.uuid4(),
                emissoes.CancelamentoIn(c_motivo="1", x_motivo=MOTIVO),
                tenant=tenant_falso(),
                db=SessaoFalsa(None),
                settings=settings_mock(),
            )

        assert erro.value.status_code == 404

    @pytest.mark.parametrize(
        ("excecao", "status_esperado", "commits", "rollbacks"),
        [
            (
                emissoes.cancelamento_service.DocumentoNaoAutorizado("fatura sem documento"),
                409,
                0,
                1,
            ),
            (emissoes.cancelamento_service.MotivoInvalido("cMotivo 3 não existe"), 422, 0, 1),
            (emissoes.cancelamento_service.ErroDeCancelamento("evento recusado"), 409, 0, 1),
            (ErroSefin(TipoErroFiscal.INDISPONIVEL, "SEFIN fora do ar"), 502, 1, 0),
        ],
    )
    async def test_erros_do_cancelamento(
        self,
        monkeypatch,
        excecao: Exception,
        status_esperado: int,
        commits: int,
        rollbacks: int,
    ) -> None:
        invoice = fatura(status=StatusFatura.AUTORIZADA)

        async def levantar(*_a: Any, **_k: Any):
            raise excecao

        monkeypatch.setattr(emissoes.cancelamento_service, "cancelar", levantar)
        sessao = SessaoFalsa(invoice)

        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.cancelar_emissao(
                invoice.id,
                emissoes.CancelamentoIn(c_motivo="1", x_motivo=MOTIVO),
                tenant=tenant_falso(invoice.tenant_id),
                db=sessao,
                settings=settings_mock(),
            )

        assert erro.value.status_code == status_esperado
        assert sessao.commits == commits
        assert sessao.rollbacks == rollbacks


class TestValidacaoDaChave:
    """A chave de idempotência é o contrato que impede nota duplicada."""

    async def test_sem_chave_da_422(self) -> None:
        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.emitir(
                entrada(),
                idempotency_key=None,
                tenant=tenant_falso(),
                db=SessaoFalsa(),
                settings=settings_mock(),
            )

        assert erro.value.status_code == 422
        assert "Idempotency-Key" in str(erro.value.detail)

    async def test_chave_curta_da_422(self) -> None:
        """A validação do schema cobre o body; o header só é validado no handler."""
        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.emitir(
                entrada(),
                idempotency_key="curta",
                tenant=tenant_falso(),
                db=SessaoFalsa(),
                settings=settings_mock(),
            )

        assert erro.value.status_code == 422
        assert "8 a 128" in str(erro.value.detail)

    async def test_chave_longa_da_422(self) -> None:
        with pytest.raises(emissoes.HTTPException) as erro:
            await emissoes.emitir(
                entrada(),
                idempotency_key="x" * 129,
                tenant=tenant_falso(),
                db=SessaoFalsa(),
                settings=settings_mock(),
            )

        assert erro.value.status_code == 422


# ---------------------------------------------------------------------------
# Serviço: montagem da DPS
# ---------------------------------------------------------------------------
def config_servico(**extra: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "ambiente": AmbienteFiscal.HOMOLOGACAO,
        "municipio_ibge": MUNICIPIO,
        "codigo_tributacao_nacional": "010701",
        "aliquota_iss": Decimal("0.05"),
        "serie_dps": 1,
        "proximo_numero_dps": 1,
        "optante_mei": False,
        "simples_nacional": False,
        "inscricao_municipal": None,
        "extra": {},
        "aderente_emissor_nacional": False,
        "aderente_confirmado_em": None,
    }
    base.update(extra)
    return SimpleNamespace(**base)


EXTRA_IBS_CBS = {"c_ind_op": "100301", "c_class_trib": "000001", "c_nbs": "123456789"}


class TestMontagemDaEntrada:
    def test_ibscbs_marca_destinatario_quando_ha_tomador(self) -> None:
        entrada_dps = emissao_service._montar_entrada(
            invoice=fatura(),
            config=config_servico(extra=dict(EXTRA_IBS_CBS)),
            numero_dps=1,
            certificado_cnpj="11222333000181",
            settings=settings_mock(),
        )

        assert entrada_dps.ibscbs is not None
        assert entrada_dps.ibscbs.ind_dest == "1", "tomador presente é o destinatário"

    def test_ibscbs_sem_tomador_marca_nao_destinatario(self) -> None:
        entrada_dps = emissao_service._montar_entrada(
            invoice=fatura(tomador_nome=None, tomador_documento=None),
            config=config_servico(extra=dict(EXTRA_IBS_CBS)),
            numero_dps=1,
            certificado_cnpj="11222333000181",
            settings=settings_mock(),
        )

        assert entrada_dps.ibscbs is not None
        assert entrada_dps.ibscbs.ind_dest == "0"
        assert entrada_dps.tomador is None

    def test_desconto_igual_ao_valor_recusa(self) -> None:
        with pytest.raises(emissao_service.ErroDeEmissao) as erro:
            emissao_service._montar_entrada(
                invoice=fatura(valor_servico="10.00", valor_desconto="10.00"),
                config=config_servico(),
                numero_dps=1,
                certificado_cnpj="11222333000181",
                settings=settings_mock(),
            )

        assert "desconto" in str(erro.value).lower()
        assert "não positivo" in str(erro.value)

    def test_desconto_menor_que_o_valor_vai_para_a_dps(self) -> None:
        entrada_dps = emissao_service._montar_entrada(
            invoice=fatura(valor_servico="10.00", valor_desconto="2.50"),
            config=config_servico(),
            numero_dps=7,
            certificado_cnpj="11222333000181",
            settings=settings_mock(),
        )

        assert entrada_dps.v_desc_incond == Decimal("2.50")
        assert entrada_dps.n_dps == 7


# ---------------------------------------------------------------------------
# Serviço: webhook tolerante a falha
# ---------------------------------------------------------------------------
class TestWebhook:
    async def test_falha_ao_enfileirar_nao_derruba_a_autorizacao(self, monkeypatch) -> None:
        """Webhook é notificação: se falhar, a nota continua autorizada (só vai para o log)."""
        from app.webhooks import service as webhook_service

        async def explodir(*_a: Any, **_k: Any):
            raise RuntimeError("fila indisponivel")

        monkeypatch.setattr(webhook_service, "enfileirar", explodir)
        invoice = fatura()
        doc = documento_da(invoice)

        await emissao_service._notificar_autorizacao(
            SessaoFalsa(), tenant_falso(invoice.tenant_id), invoice, doc
        )

    async def test_enfileirar_recebe_payload_da_nota(self, monkeypatch) -> None:
        from app.webhooks import service as webhook_service

        capturado: dict[str, Any] = {}

        async def capturar(sessao, tenant, *, tipo_evento: str, payload: dict[str, Any]):
            capturado.update({"tipo": tipo_evento, "payload": payload})

        monkeypatch.setattr(webhook_service, "enfileirar", capturar)
        invoice = fatura()
        doc = documento_da(invoice)

        await emissao_service._notificar_autorizacao(
            SessaoFalsa(), tenant_falso(invoice.tenant_id), invoice, doc
        )

        assert capturado["tipo"] == "nfse.autorizada"
        assert capturado["payload"]["chave"] == CHAVE_MOCK
        assert capturado["payload"]["invoice_id"] == str(invoice.id)
        assert capturado["payload"]["tipo_documento"] == TipoDocumento.NFSE.value


# ---------------------------------------------------------------------------
# Serviço: `emitir` de ponta a ponta com dublês
# ---------------------------------------------------------------------------
@pytest.fixture
def servico_dublado(monkeypatch):
    """Serialização, assinatura e certificado dublados; o resto do serviço é real."""
    from app.webhooks import service as webhook_service

    async def ativo(_sessao, _tenant_id):
        return SimpleNamespace(id=uuid.uuid4())

    async def abrir(_sessao, registro, **_k: Any):
        return SimpleNamespace(cnpj="11222333000181")

    async def sem_webhook(*_a: Any, **_k: Any):
        return None

    monkeypatch.setattr(emissao_service.certificados, "ativo", ativo)
    monkeypatch.setattr(emissao_service.certificados, "abrir_para_uso", abrir)
    monkeypatch.setattr(emissao_service, "dps_para_bytes", lambda entrada: b"<DPS/>")
    monkeypatch.setattr(emissao_service, "assinar_dps", lambda xml, cert: b"<DPS assinada/>")
    monkeypatch.setattr(emissao_service, "extrair_id", lambda xml: "DPS123")
    monkeypatch.setattr(webhook_service, "enfileirar", sem_webhook)
    return monkeypatch


def sessao_do_servico(*configs: Any, numero_dps: int = 41) -> SessaoFalsa:
    """Ordem das consultas em `servico.emitir`: documento, configuração, contador de DPS."""
    sessao = SessaoFalsa(None, list(configs), numero_dps)
    return sessao


class AdapterFalso:
    def __init__(
        self, resposta: RespostaEmissao | None = None, erro: Exception | None = None
    ) -> None:
        self.resposta = resposta or RespostaEmissao(chave_acesso=CHAVE_MOCK, nfse_xml=b"<NFSe/>")
        self.erro = erro
        self.emitidos: list[bytes] = []
        self.fechado = False

    def emitir(self, dps_assinada: bytes) -> RespostaEmissao:
        self.emitidos.append(dps_assinada)
        if self.erro is not None:
            raise self.erro
        return self.resposta

    def consultar_dps(self, id_dps: str) -> str | None:
        return None

    def consultar_nfse(self, chave: str) -> RespostaEmissao:
        raise ErroSefin(TipoErroFiscal.INDISPONIVEL, "ADN fora")

    def fechar(self) -> None:
        self.fechado = True


class TestServicoEmitir:
    async def test_rota_nao_confirmada_em_homologacao_emite_com_aviso(
        self, servico_dublado
    ) -> None:
        """Fora de produção, ausência de confirmação é aviso — senão instalação nova não testa."""
        invoice = fatura()
        sessao = sessao_do_servico(config_servico())
        adapter = AdapterFalso()

        doc = await emissao_service.emitir(
            sessao, tenant_falso(invoice.tenant_id), invoice, adapter=adapter
        )

        assert doc.chave == CHAVE_MOCK
        assert invoice.status is StatusFatura.AUTORIZADA
        assert adapter.emitidos, "a DPS assinada precisa chegar ao adapter"
        assert adapter.emitidos[0] == b"<DPS assinada/>"
        assert not adapter.fechado, "adapter do chamador não é fechado pelo serviço"
        tipos = [evento.tipo for evento in sessao.adicionados if isinstance(evento, InvoiceEvent)]
        assert "autorizada" in tipos

    async def test_rota_bloqueada_recusa_antes_de_assinar(self, servico_dublado) -> None:
        """Preflight de rota (§77): bloqueia antes de gerar, assinar e transmitir."""
        config = config_servico(
            ambiente=AmbienteFiscal.PRODUCAO,
            aderente_emissor_nacional=False,
            aderente_confirmado_em=None,
            simples_nacional=False,
        )
        invoice = fatura(ambiente=AmbienteFiscal.PRODUCAO)
        adapter = AdapterFalso()

        with pytest.raises(emissao_service.RotaNaoPermitida) as erro:
            await emissao_service.emitir(
                sessao_do_servico(config),
                tenant_falso(invoice.tenant_id),
                invoice,
                adapter=adapter,
            )

        assert erro.value.pendencia, "sem pendência o operador teria que adivinhar o que falta"
        assert "aderente_confirmado_em" in str(erro.value.pendencia)
        assert not adapter.emitidos, "nada pode ser transmitido com a rota bloqueada"
        assert invoice.status is StatusFatura.PENDENTE

    async def test_erro_de_dps_registra_evento_e_marca_erro(
        self, servico_dublado, monkeypatch
    ) -> None:
        def quebrar(_entrada):
            raise emissao_service.ErroDps("campo obrigatório ausente")

        monkeypatch.setattr(emissao_service, "dps_para_bytes", quebrar)
        invoice = fatura()
        sessao = sessao_do_servico(config_servico())

        with pytest.raises(emissao_service.ErroDeEmissao) as erro:
            await emissao_service.emitir(
                sessao, tenant_falso(invoice.tenant_id), invoice, adapter=AdapterFalso()
            )

        assert "campo obrigatório ausente" in str(erro.value)
        assert invoice.status is StatusFatura.ERRO
        assert invoice.erro == "campo obrigatório ausente"
        tipos = [evento.tipo for evento in sessao.adicionados if isinstance(evento, InvoiceEvent)]
        assert "erro_local" in tipos

    async def test_timeout_ambiguo_recupera_nota_ja_gerada(self, servico_dublado) -> None:
        """Reenviar sem consultar duplicaria documento: o serviço consulta antes de acusar falha."""
        resposta = RespostaEmissao(chave_acesso="9" * 50, nfse_xml=b"<NFSe/>", id_dps="DPS123")

        class AdapterComNota(AdapterFalso):
            def __init__(self) -> None:
                super().__init__(erro=ErroSefin(TipoErroFiscal.AMBIGUO, "timeout na SEFIN"))

            def consultar_dps(self, id_dps: str) -> str | None:
                assert id_dps == "DPS123"
                return "9" * 50

            def consultar_nfse(self, chave: str) -> RespostaEmissao:
                assert chave == "9" * 50
                return resposta

        invoice = fatura()
        adapter = AdapterComNota()
        sessao = sessao_do_servico(config_servico())

        doc = await emissao_service.emitir(
            sessao,
            tenant_falso(invoice.tenant_id),
            invoice,
            adapter=adapter,
        )

        assert doc.chave == "9" * 50, "a nota recuperada é a mesma que a SEFIN gerou"
        assert invoice.status is StatusFatura.AUTORIZADA
        tipos = [evento.tipo for evento in sessao.adicionados if isinstance(evento, InvoiceEvent)]
        assert "autorizada" in tipos
        assert "erro_sefin" not in tipos, "não houve falha a registrar: a nota existe"

    async def test_timeout_ambiguo_sem_nota_deixa_fatura_em_processamento(
        self, servico_dublado
    ) -> None:
        """Timeout ambíguo cuja DPS não gerou NFS-e.

        Comportamento atual (auditado, não corrigido aqui): o `raise` do caminho de
        recuperação não passa por `_registrar_falha`, então a fatura fica em
        `PROCESSANDO` e **nenhum** evento de erro é gravado — o operador vê a fatura
        travada sem explicação. O teste retrata o estado de hoje.
        """
        invoice = fatura()
        adapter = AdapterFalso(erro=ErroSefin(TipoErroFiscal.AMBIGUO, "timeout na SEFIN"))
        sessao = sessao_do_servico(config_servico())

        with pytest.raises(ErroSefin):
            await emissao_service.emitir(
                sessao, tenant_falso(invoice.tenant_id), invoice, adapter=adapter
            )

        assert invoice.status is StatusFatura.PROCESSANDO
        tipos = [evento.tipo for evento in sessao.adicionados if isinstance(evento, InvoiceEvent)]
        assert "erro_sefin" not in tipos, "falha ambígua sem nota não é registrada hoje"

    async def test_rejeicao_marca_rejeitada(self, servico_dublado) -> None:
        invoice = fatura()
        adapter = AdapterFalso(erro=ErroSefin(TipoErroFiscal.REJEICAO, "E0429 aliquota"))

        with pytest.raises(ErroSefin):
            await emissao_service.emitir(
                sessao_do_servico(config_servico()),
                tenant_falso(invoice.tenant_id),
                invoice,
                adapter=adapter,
            )

        assert invoice.status is StatusFatura.REJEITADA

    async def test_cliente_proprio_e_fechado(self, servico_dublado, monkeypatch) -> None:
        """Sem adapter do chamador, o serviço constrói o cliente mTLS — e precisa fechá-lo."""
        criados: list[Any] = []

        class ClienteProprio(AdapterFalso):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__()
                self.args = args
                self.kwargs = kwargs
                criados.append(self)

        monkeypatch.setattr(emissao_service, "SefinNacionalClient", ClienteProprio)
        invoice = fatura()

        doc = await emissao_service.emitir(
            sessao_do_servico(config_servico()), tenant_falso(invoice.tenant_id), invoice
        )

        assert doc.chave == CHAVE_MOCK
        assert len(criados) == 1
        assert criados[0].fechado is True, "cliente criado pelo serviço não pode vazar conexão"

    async def test_documento_ja_existente_encerra_sem_emitir(self, servico_dublado) -> None:
        """Idempotência: documento com chave já gravado devolve o mesmo, sem nova transmissão."""
        invoice = fatura()
        existente = documento_da(invoice)
        adapter = AdapterFalso()

        doc = await emissao_service.emitir(
            SessaoFalsa(existente),
            tenant_falso(invoice.tenant_id),
            invoice,
            adapter=adapter,
        )

        assert doc is existente
        assert not adapter.emitidos

    async def test_chave_no_body_e_depois_no_header_nao_e_conflito(self, cliente, pronto) -> None:
        """Mesma chave por canais diferentes é o mesmo pedido — 200, não 409 (§101).

        Antes, o `payload` guardava o body inteiro, incluindo `idempotency_key`. O primeiro envio
        levava a chave no body e o segundo no header (ambos contratos válidos, o header vence); a
        comparação via diferença de campo e respondia 409 "corpo diferente" para um reenvio legítimo.
        """
        corpo = corpo_emissao("chave-dois-canais")
        primeira = await cliente.post(
            "/v1/emissoes", json=corpo, headers=cabecalho(pronto["tenant"])
        )
        assert primeira.status_code == 201, primeira.text

        # Mesmo pedido de negócio; a chave agora só no header.
        corpo_sem_chave = {k: v for k, v in corpo.items() if k != "idempotency_key"}
        segunda = await cliente.post(
            "/v1/emissoes",
            json=corpo_sem_chave,
            headers={**pronto["cabecalho"], "Idempotency-Key": "chave-dois-canais"},
        )

        assert segunda.status_code == 200, segunda.text
        assert segunda.json()["ja_existia"] is True

    async def test_corpo_realmente_diferente_continua_409(self, cliente, pronto) -> None:
        """A correção não pode cegar a comparação: valor diferente é 409."""
        primeira = await emitir(cliente, pronto["tenant"], "chave-corpo-diferente")
        assert primeira.status_code == 201, primeira.text

        segunda = await cliente.post(
            "/v1/emissoes",
            json=corpo_emissao("chave-corpo-diferente", valor="99.00"),
            headers={**pronto["cabecalho"], "Idempotency-Key": "chave-corpo-diferente"},
        )

        assert segunda.status_code == 409, segunda.text
        assert "corpo diferente" in segunda.text
