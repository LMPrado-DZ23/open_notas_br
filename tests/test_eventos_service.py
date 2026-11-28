"""Registro de evento genérico da NFS-e — o catálogo decide, o serviço recusa o resto.

Duas guardas que evitam chamada inútil e erro genérico da SEFIN:

1. **cancelamento não passa por aqui** — tem rota própria porque muda status e valida motivo;
2. **evento de ofício não é do contribuinte** — quem dispara é o fisco.

Nenhum certificado real e nenhuma chamada de rede: o adaptador é dublê.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.db.models.enums import StatusFatura
from app.db.models.invoice import Invoice
from app.nfse import eventos as servico
from app.nfse.adapter import RespostaEvento
from app.nfse.errors import ErroSefin, TipoErroFiscal
from app.nfse.eventos_tipos import ErroDeEventoCatalogo

TENANT = SimpleNamespace(id=uuid.uuid4())
CONF = SimpleNamespace(sefin_base_url="", sefin_permitir_host_nao_oficial=False)
CODIGO_CONTRIBUINTE = "105102"
CODIGO_OFICIO = "101103"


class ResultadoFalso:
    def __init__(self, item=None, escalar: int = 0) -> None:
        self._item = item
        self._escalar = escalar

    def scalars(self) -> ResultadoFalso:
        return self

    def first(self):
        return self._item

    def scalar_one(self) -> int:
        return self._escalar


class SessaoFila:
    def __init__(self, *resultados) -> None:
        self._fila = list(resultados)
        self.adicionados: list = []
        self.flushes = 0

    def add(self, objeto: object) -> None:
        self.adicionados.append(objeto)

    async def flush(self) -> None:
        self.flushes += 1

    async def execute(self, consulta: object) -> ResultadoFalso:
        return self._fila.pop(0) if self._fila else ResultadoFalso()


def _invoice() -> Invoice:
    return Invoice(
        id=uuid.uuid4(),
        tenant_id=TENANT.id,
        idempotency_key="k1",
        status=StatusFatura.AUTORIZADA,
        valor_servico="10.00",
        descricao_servico="servico",
        competencia="2026-11",
    )


def _documento(ambiente: str = "homologacao") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), chave="5200258" + "1" * 43, ambiente=SimpleNamespace(value=ambiente)
    )


class TestValidarTipo:
    def test_cancelamento_e_reservado(self) -> None:
        with pytest.raises(servico.TipoReservado) as erro:
            servico.validar_tipo(servico.CANCELAMENTO)

        assert "rota própria" in str(erro.value)

    def test_codigo_inexistente_recusa(self) -> None:
        with pytest.raises(ErroDeEventoCatalogo):
            servico.validar_tipo("999999")

    def test_evento_de_oficio_recusa_por_padrao(self) -> None:
        with pytest.raises(servico.EventoNaoAplicavel) as erro:
            servico.validar_tipo(CODIGO_OFICIO)

        assert "de ofício" in str(erro.value)

    def test_evento_de_oficio_aceito_com_permissao(self) -> None:
        servico.validar_tipo(CODIGO_OFICIO, permitir_oficio=True)

    def test_evento_do_contribuinte_passa(self) -> None:
        servico.validar_tipo(CODIGO_CONTRIBUINTE)


class TestDocumento:
    async def test_sem_documento_recusa(self) -> None:
        with pytest.raises(servico.ErroDeEvento) as erro:
            await servico._documento_autorizado(SessaoFila(), TENANT.id, _invoice())

        assert "não há nota" in str(erro.value)


def _preparar(monkeypatch, *, certificado=None, erro=None):
    monkeypatch.setattr(servico.certificados, "ativo", lambda *a: _async(SimpleNamespace(id="c")))
    monkeypatch.setattr(
        servico.certificados,
        "abrir_para_uso",
        lambda *a, **k: _async(certificado or SimpleNamespace(cnpj="64339333000122")),
    )
    monkeypatch.setattr(servico, "construir_evento", lambda *a, **k: b"<evento/>")
    monkeypatch.setattr(servico, "assinar_pedido_evento", lambda xml, cert: xml)

    class AdapterFalso:
        def __init__(self) -> None:
            self.chamadas: list = []

        def registrar_evento(self, chave, xml, operacao=""):
            self.chamadas.append(operacao)
            if erro is not None:
                raise erro
            return RespostaEvento(evento_xml=b"<e/>", data_processamento="2026-11-28")

        def fechar(self) -> None:
            return None

    return AdapterFalso()


class TestRegistrar:
    async def test_sem_certificado_ativo_recusa(self, monkeypatch) -> None:
        monkeypatch.setattr(servico.certificados, "ativo", lambda *a: _async(None))

        with pytest.raises(servico.ErroDeEvento) as erro:
            await servico.registrar(
                SessaoFila(ResultadoFalso(_documento())),
                TENANT,
                _invoice(),
                codigo=CODIGO_CONTRIBUINTE,
                campos={},
                settings=CONF,
            )

        assert "certificado A1 ativo" in str(erro.value)

    async def test_certificado_sem_cnpj_recusa(self, monkeypatch) -> None:
        monkeypatch.setattr(
            servico.certificados, "ativo", lambda *a: _async(SimpleNamespace(id="c"))
        )
        monkeypatch.setattr(
            servico.certificados,
            "abrir_para_uso",
            lambda *a, **k: _async(SimpleNamespace(cnpj=None)),
        )

        with pytest.raises(servico.ErroDeEvento) as erro:
            await servico.registrar(
                SessaoFila(ResultadoFalso(_documento())),
                TENANT,
                _invoice(),
                codigo=CODIGO_CONTRIBUINTE,
                campos={},
                settings=CONF,
            )

        assert "não identifica CNPJ" in str(erro.value)

    async def test_erro_de_payload_sobe_sem_virar_conflito(self, monkeypatch) -> None:
        monkeypatch.setattr(
            servico.certificados, "ativo", lambda *a: _async(SimpleNamespace(id="c"))
        )
        monkeypatch.setattr(
            servico.certificados,
            "abrir_para_uso",
            lambda *a, **k: _async(SimpleNamespace(cnpj="64339333000122")),
        )

        def construir(*a, **k):
            raise ErroDeEventoCatalogo("campo obrigatório ausente")

        monkeypatch.setattr(servico, "construir_evento", construir)

        with pytest.raises(ErroDeEventoCatalogo):
            await servico.registrar(
                SessaoFila(ResultadoFalso(_documento())),
                TENANT,
                _invoice(),
                codigo=CODIGO_CONTRIBUINTE,
                campos={},
                settings=CONF,
            )

    async def test_sucesso_registra_com_sequencia(self, monkeypatch) -> None:
        adapter = _preparar(monkeypatch)
        sessao = SessaoFila(ResultadoFalso(_documento()), ResultadoFalso(escalar=2))
        invoice = _invoice()

        resposta = await servico.registrar(
            sessao,
            TENANT,
            invoice,
            codigo=CODIGO_CONTRIBUINTE,
            campos={"xCampo": "1"},
            adapter=adapter,
            settings=CONF,
        )

        assert resposta.data_processamento
        eventos = [e for e in sessao.adicionados if e.tipo == f"evento_{CODIGO_CONTRIBUINTE}"]
        assert eventos and eventos[0].sequencia == 3, "sequência começa em max+1"
        assert adapter.chamadas == [f"evento {CODIGO_CONTRIBUINTE}"]

    async def test_falha_da_sefin_preserva_trilha(self, monkeypatch) -> None:
        erro = ErroSefin(tipo=TipoErroFiscal.INDISPONIVEL, resumo="fora do ar", http_status=503)
        adapter = _preparar(monkeypatch, erro=erro)
        sessao = SessaoFila(ResultadoFalso(_documento()))

        with pytest.raises(ErroSefin):
            await servico.registrar(
                sessao,
                TENANT,
                _invoice(),
                codigo=CODIGO_CONTRIBUINTE,
                campos={},
                adapter=adapter,
                settings=CONF,
            )

        falhas = [e for e in sessao.adicionados if e.tipo == f"evento_{CODIGO_CONTRIBUINTE}_falhou"]
        assert falhas and falhas[0].status == "falhou"

    async def test_sem_adapter_monta_e_fecha_cliente(self, monkeypatch) -> None:
        _preparar(monkeypatch)
        fechados: list[bool] = []

        class ClienteFalso:
            def __init__(self, *a, **k) -> None:
                pass

            def registrar_evento(self, chave, xml, operacao=""):
                return RespostaEvento(evento_xml=b"<e/>", data_processamento="2026-11-28")

            def fechar(self) -> None:
                fechados.append(True)

        monkeypatch.setattr("app.nfse.adapter.SefinNacionalClient", ClienteFalso)

        await servico.registrar(
            SessaoFila(ResultadoFalso(_documento()), ResultadoFalso()),
            TENANT,
            _invoice(),
            codigo=CODIGO_CONTRIBUINTE,
            campos={},
            settings=CONF,
        )

        assert fechados == [True]


class TestTiposDisponiveis:
    def test_exclui_cancelamento(self) -> None:
        assert servico.CANCELAMENTO not in servico.tipos_disponiveis()

    def test_inclui_oficio_quando_pedido(self) -> None:
        com_oficio = servico.tipos_disponiveis(incluir_oficio=True)
        sem_oficio = servico.tipos_disponiveis()

        assert len(com_oficio) >= len(sem_oficio)
        assert CODIGO_OFICIO in com_oficio and CODIGO_OFICIO not in sem_oficio


async def _async(valor):
    return valor
