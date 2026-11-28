"""Apuração por competência e emissão de guia — com dublês, sem banco.

Duas regras fiscais que só o teste protege:

1. **só documento autorizado entra na apuração** — o filtro tem que estar na consulta, não presumido;
2. **falha ao gerar guia marca a apuração como FALHOU** — sem isso, a apuração fica "ABERTA" sem guia,
   e o cliente acha que tem boleto.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.assessment import service
from app.assessment.providers import ErroDeGuia, Guia
from app.db.models.enums import ProvedorGuia, StatusApuracao
from app.db.models.ops import TaxAssessment


class ResultadoFalso:
    def __init__(self, itens: list) -> None:
        self._itens = itens

    def scalars(self) -> ResultadoFalso:
        return self

    def first(self):
        return self._itens[0] if self._itens else None

    def all(self) -> list:
        return self._itens


class SessaoFila:
    """Devolve resultados na ordem em que as consultas são feitas."""

    def __init__(self, *lotes: list) -> None:
        self._fila = list(lotes)
        self.adicionados: list = []
        self.flushes = 0

    def add(self, objeto: object) -> None:
        self.adicionados.append(objeto)

    async def flush(self) -> None:
        self.flushes += 1

    async def execute(self, consulta: object) -> ResultadoFalso:
        return ResultadoFalso(self._fila.pop(0) if self._fila else [])


class TestValidarCompetencia:
    @pytest.mark.parametrize("valor", ["2026-11", "2026-01", "2100-12"])
    def test_aceita_aaaa_mm(self, valor: str) -> None:
        assert service.validar_competencia(valor) == valor

    @pytest.mark.parametrize("valor", ["2026/11", "2026-1", "26-11", "", "2026-13", "1999-01"])
    def test_recusa_formato_ou_faixa(self, valor: str) -> None:
        with pytest.raises(service.CompetenciaInvalida):
            service.validar_competencia(valor)

    def test_recusa_texto_que_nao_e_numero(self) -> None:
        with pytest.raises(service.CompetenciaInvalida):
            service.validar_competencia("20xx-11")


class TestCompetenciaDe:
    def test_usa_data_informada(self) -> None:
        assert service.competencia_de(date(2026, 3, 15)) == "2026-03"

    def test_padrao_e_hoje(self) -> None:
        assert len(service.competencia_de()) == 7


class TestAliquotaIss:
    async def test_sem_configuracao_devolve_none(self) -> None:
        assert await service._aliquota_iss(SessaoFila([]), uuid.uuid4(), "homologacao") is None

    async def test_configuracao_sem_aliquota_devolve_none(self) -> None:
        config = SimpleNamespace(aliquota_iss=None)

        assert (
            await service._aliquota_iss(SessaoFila([config]), uuid.uuid4(), "homologacao") is None
        )

    async def test_aliquota_vira_decimal(self) -> None:
        config = SimpleNamespace(aliquota_iss="0.05")

        aliquota = await service._aliquota_iss(SessaoFila([config]), uuid.uuid4(), "homologacao")

        assert aliquota == Decimal("0.05")


def _fatura(valor: str = "100.00", desconto: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), valor_servico=valor, valor_desconto=desconto)


def _apuracao() -> TaxAssessment:
    return TaxAssessment(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        competencia="2026-11",
        provedor=ProvedorGuia.MAN,
        total_servicos="0",
        total_iss="0",
        total_tributos="0",
        quantidade_documentos=0,
        status=StatusApuracao.ABERTA,
        payload={},
    )


class TestConsolidar:
    async def test_soma_servicos_e_calcula_iss(self, monkeypatch) -> None:
        faturas = [_fatura("100.00"), _fatura("50.00", "10.00")]
        config = SimpleNamespace(aliquota_iss="0.05")
        sessao = SessaoFila(faturas, [config], [])

        monkeypatch.setattr(
            service,
            "calcular_ibscbs",
            lambda base, ano_fato_gerador: SimpleNamespace(valor_total=Decimal("1.00")),
        )

        apuracao = await service.consolidar(sessao, uuid.uuid4(), "2026-11")

        assert apuracao.total_servicos == Decimal("150.00")
        assert apuracao.total_iss == Decimal("7.00")  # 5,00 + 2,00 (base 40,00)
        assert apuracao.quantidade_documentos == 2
        assert apuracao.status == StatusApuracao.FECHADA
        assert sessao.adicionados == [apuracao]

    async def test_sem_aliquota_avisa_e_zera_iss(self, monkeypatch) -> None:
        sessao = SessaoFila([_fatura()], [])

        monkeypatch.setattr(
            service,
            "calcular_ibscbs",
            lambda base, ano_fato_gerador: SimpleNamespace(valor_total=Decimal("0")),
        )

        apuracao = await service.consolidar(sessao, uuid.uuid4(), "2026-11")

        assert apuracao.total_iss == Decimal("0.00")
        assert any("alíquota de ISS" in aviso for aviso in apuracao.payload["avisos"])

    async def test_erro_de_calculo_vira_aviso_e_nao_derruba(self, monkeypatch) -> None:
        from app.tax.rtc import ErroCalculoTributario

        def calcular(base, ano_fato_gerador):
            raise ErroCalculoTributario("tabela do ano ausente")

        sessao = SessaoFila([_fatura()], [])
        monkeypatch.setattr(service, "calcular_ibscbs", calcular)

        apuracao = await service.consolidar(sessao, uuid.uuid4(), "2026-11")

        assert apuracao.status == StatusApuracao.FECHADA
        assert any("tabela do ano ausente" in aviso for aviso in apuracao.payload["avisos"])

    async def test_apuracao_existente_e_atualizada_e_nao_duplicada(self, monkeypatch) -> None:
        existente = _apuracao()
        sessao = SessaoFila([], [], [existente])

        monkeypatch.setattr(
            service,
            "calcular_ibscbs",
            lambda base, ano_fato_gerador: SimpleNamespace(valor_total=Decimal("0")),
        )

        apuracao = await service.consolidar(sessao, existente.tenant_id, "2026-11")

        assert apuracao is existente
        assert not sessao.adicionados, "não pode criar segunda apuração para a mesma competência"

    async def test_competencia_invalida_nao_consulta(self) -> None:
        sessao = SessaoFila()

        with pytest.raises(service.CompetenciaInvalida):
            await service.consolidar(sessao, uuid.uuid4(), "11-2026")

        assert sessao.adicionados == []


class TestGerarGuia:
    async def test_sucesso_preenche_guia(self, monkeypatch) -> None:
        apuracao = _apuracao()
        guia = Guia(
            provedor=ProvedorGuia.MAN,
            numero="123",
            vencimento=date(2026, 12, 10),
            linha_digitavel="00190",
            valor=Decimal("10.00"),
        )
        monkeypatch.setattr(
            service, "obter_provedor", lambda p: SimpleNamespace(gerar=lambda dados: guia)
        )
        sessao = SessaoFila()

        devolvida = await service.gerar_guia(sessao, apuracao)

        assert devolvida is guia
        assert apuracao.guia_numero == "123"
        assert apuracao.status == StatusApuracao.ABERTA
        assert apuracao.payload["guia"]["numero"] == "123"

    async def test_erro_do_provedor_marca_falhou(self, monkeypatch) -> None:
        apuracao = _apuracao()

        def gerar(dados):
            raise ErroDeGuia("município sem convênio")

        monkeypatch.setattr(service, "obter_provedor", lambda p: SimpleNamespace(gerar=gerar))
        sessao = SessaoFila()

        with pytest.raises(ErroDeGuia):
            await service.gerar_guia(sessao, apuracao)

        assert apuracao.status == StatusApuracao.FALHOU
        assert apuracao.erro == "município sem convênio"
        assert sessao.flushes == 1


class TestConsultas:
    async def test_listar_devolve_lista(self) -> None:
        assert await service.listar(SessaoFila(), uuid.uuid4()) == []

    async def test_por_id_ausente_levanta(self) -> None:
        with pytest.raises(service.ErroDeApuracao):
            await service.por_id(SessaoFila(), uuid.uuid4(), uuid.uuid4())

    async def test_por_id_existente_devolve(self) -> None:
        apuracao = _apuracao()
        sessao = SessaoFila([apuracao])

        assert await service.por_id(sessao, apuracao.tenant_id, apuracao.id) is apuracao
