"""Cancelamento de NFS-e — as quatro guardas que evitam evento inválido na SEFIN.

`cancelar` recusa antes de chamar a rede quando: a fatura já está cancelada, não há documento com
chave, o motivo é inválido, não há A1 ativo, ou o A1 não identifica CNPJ. Cada uma dessas guardas
existe porque a alternativa custa uma tentativa da cota e devolve erro genérico.

Testado com dublês: nenhum certificado real, nenhuma chamada à SEFIN.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.db.models.enums import StatusFatura
from app.db.models.invoice import Invoice
from app.nfse import cancelamento as servico
from app.nfse.adapter import RespostaEvento
from app.nfse.errors import ErroSefin, TipoErroFiscal


class ResultadoFalso:
    def __init__(self, item=None) -> None:
        self._item = item

    def scalars(self) -> ResultadoFalso:
        return self

    def first(self):
        return self._item


class SessaoFalsa:
    def __init__(self, documento=None) -> None:
        self._documento = documento
        self.adicionados: list = []
        self.flushes = 0

    def add(self, objeto: object) -> None:
        self.adicionados.append(objeto)

    async def flush(self) -> None:
        self.flushes += 1

    async def execute(self, consulta: object) -> ResultadoFalso:
        return ResultadoFalso(self._documento)


TENANT = SimpleNamespace(id=uuid.uuid4())
CONF = SimpleNamespace(sefin_base_url="", sefin_permitir_host_nao_oficial=False)


def _invoice(status: StatusFatura = StatusFatura.AUTORIZADA) -> Invoice:
    return Invoice(
        id=uuid.uuid4(),
        tenant_id=TENANT.id,
        idempotency_key="k1",
        status=status,
        valor_servico="10.00",
        descricao_servico="servico",
        competencia="2026-11",
    )


def _documento(ambiente: str = "homologacao") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        chave="5200258" + "1" * 43,
        ambiente=SimpleNamespace(value=ambiente),
        cancelado_em=None,
    )


class CertificadoFalso:
    cnpj = "64339333000122"


def _preparar(monkeypatch, *, certificado=None, documento_ok=True, erro=None):
    # A assinatura é provada em test_evento_*.py; aqui o alvo é o fluxo do cancelamento.
    monkeypatch.setattr(servico, "assinar_pedido_evento", lambda xml, cert: xml)
    monkeypatch.setattr(
        servico.certificados, "ativo", lambda sessao, tenant_id: _async(SimpleNamespace(id="c"))
    )
    monkeypatch.setattr(
        servico.certificados,
        "abrir_para_uso",
        lambda *a, **k: _async(certificado or CertificadoFalso()),
    )

    class AdapterFalso:
        def __init__(self) -> None:
            self.chamadas: list = []

        def registrar_evento(self, chave, xml):
            self.chamadas.append((chave, xml))
            if erro is not None:
                raise erro
            return RespostaEvento(evento_xml=b"<evento/>", data_processamento="2026-11-28T10:00:00")

        def fechar(self) -> None:
            return None

    return AdapterFalso()


class TestDocumentoAutorizado:
    async def test_sem_documento_recusa(self) -> None:
        with pytest.raises(servico.DocumentoNaoAutorizado):
            await servico._documento_autorizado(SessaoFalsa(None), TENANT.id, _invoice())

    async def test_com_chave_devolve(self) -> None:
        documento = _documento()

        alvo = await servico._documento_autorizado(SessaoFalsa(documento), TENANT.id, _invoice())

        assert alvo.chave == documento.chave


class TestMotivo:
    @pytest.mark.parametrize("codigo", ["", "3", "99", None])
    def test_codigo_fora_da_tabela_recusa(self, codigo) -> None:
        with pytest.raises(servico.MotivoInvalido):
            servico.validar_motivo(codigo, "motivo suficientemente longo")

    def test_motivo_curto_recusa(self) -> None:
        with pytest.raises(servico.MotivoInvalido):
            servico.validar_motivo("1", "curto")

    def test_motivo_valido_passa(self) -> None:
        servico.validar_motivo("1", "erro na digitacao do valor")


class TestCancelar:
    async def test_ja_cancelada_recusa_antes_de_tudo(self) -> None:
        with pytest.raises(servico.ErroDeCancelamento) as erro:
            await servico.cancelar(
                SessaoFalsa(),
                TENANT,
                _invoice(StatusFatura.CANCELADA),
                c_motivo="1",
                x_motivo="erro na emissao do documento",
                settings=CONF,
            )

        assert "já está cancelada" in str(erro.value)

    async def test_sem_certificado_ativo_recusa(self, monkeypatch) -> None:
        monkeypatch.setattr(servico.certificados, "ativo", lambda *a: _async(None))

        with pytest.raises(servico.ErroDeCancelamento) as erro:
            await servico.cancelar(
                SessaoFalsa(_documento()),
                TENANT,
                _invoice(),
                c_motivo="1",
                x_motivo="erro na emissao do documento",
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

        with pytest.raises(servico.ErroDeCancelamento) as erro:
            await servico.cancelar(
                SessaoFalsa(_documento()),
                TENANT,
                _invoice(),
                c_motivo="1",
                x_motivo="erro na emissao do documento",
                settings=CONF,
            )

        assert "não identifica CNPJ" in str(erro.value)

    async def test_sucesso_marca_cancelada_e_registra_evento(self, monkeypatch) -> None:
        adapter = _preparar(monkeypatch)
        invoice = _invoice()
        documento = _documento()
        sessao = SessaoFalsa(documento)

        resposta = await servico.cancelar(
            sessao,
            TENANT,
            invoice,
            c_motivo="1",
            x_motivo="erro na emissao do documento",
            adapter=adapter,
            settings=CONF,
        )

        assert resposta.data_processamento
        assert invoice.status is StatusFatura.CANCELADA
        assert documento.cancelado_em is not None
        eventos = [e for e in sessao.adicionados if getattr(e, "tipo", None) == "cancelamento"]
        assert eventos and eventos[0].status == "registrado"
        assert len(adapter.chamadas) == 1

    async def test_falha_da_sefin_preserva_tentativa_e_nao_cancela(self, monkeypatch) -> None:
        erro = ErroSefin(
            tipo=TipoErroFiscal.INDISPONIVEL,
            resumo="autorizador fora do ar",
            http_status=503,
        )
        adapter = _preparar(monkeypatch, erro=erro)
        invoice = _invoice()
        sessao = SessaoFalsa(_documento())

        with pytest.raises(ErroSefin):
            await servico.cancelar(
                sessao,
                TENANT,
                invoice,
                c_motivo="1",
                x_motivo="erro na emissao do documento",
                adapter=adapter,
                settings=CONF,
            )

        assert invoice.status is StatusFatura.AUTORIZADA, "falha não pode cancelar a nota"
        falhas = [
            e for e in sessao.adicionados if getattr(e, "tipo", None) == "cancelamento_falhou"
        ]
        assert falhas and falhas[0].status == "falhou"

    async def test_motivo_invalido_nao_chama_sefin(self, monkeypatch) -> None:
        adapter = _preparar(monkeypatch)

        with pytest.raises(servico.MotivoInvalido):
            await servico.cancelar(
                SessaoFalsa(_documento()),
                TENANT,
                _invoice(),
                c_motivo="3",
                x_motivo="motivo qualquer longo o bastante",
                adapter=adapter,
                settings=CONF,
            )

        assert adapter.chamadas == []

    async def test_erro_ao_montar_evento_vira_motivo_invalido(self, monkeypatch) -> None:
        """Falha de construção/assinatura acontece antes da rede e vira erro de motivo."""
        from app.nfse.evento import ErroDeEvento

        _preparar(monkeypatch)

        def explodir(xml, cert):
            raise ErroDeEvento("xMotivo não pode conter quebra de linha")

        monkeypatch.setattr(servico, "assinar_pedido_evento", explodir)

        with pytest.raises(servico.MotivoInvalido) as erro:
            await servico.cancelar(
                SessaoFalsa(_documento()),
                TENANT,
                _invoice(),
                c_motivo="1",
                x_motivo="erro na emissao do documento",
                settings=CONF,
            )

        assert "quebra de linha" in str(erro.value)

    async def test_sem_adapter_monta_cliente_e_fecha(self, monkeypatch) -> None:
        """Caminho de produção: o cliente real é montado e precisa ser fechado no `finally`."""
        _preparar(monkeypatch)
        fechados: list[bool] = []
        registrados: list = []

        class ClienteFalso:
            def __init__(self, *a, **k) -> None:
                pass

            def registrar_evento(self, chave, xml):
                registrados.append(chave)
                return RespostaEvento(evento_xml=b"<e/>", data_processamento="2026-11-28")

            def fechar(self) -> None:
                fechados.append(True)

        monkeypatch.setattr("app.nfse.adapter.SefinNacionalClient", ClienteFalso)

        await servico.cancelar(
            SessaoFalsa(_documento()),
            TENANT,
            _invoice(),
            c_motivo="2",
            x_motivo="servico nao foi prestado ao cliente",
            settings=CONF,
        )

        assert registrados and fechados == [True]


async def _async(valor):
    return valor
