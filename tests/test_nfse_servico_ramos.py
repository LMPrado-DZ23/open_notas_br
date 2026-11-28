"""Serviço de emissão: configuração fiscal, montagem da DPS e recuperação após timeout.

Os ramos cobertos aqui são os que evitam nota errada:

- configuração **ambígua** (tenant com dois municípios) não escolhe sozinha — exige `municipio_ibge`;
- IBS/CBS **incompleto** é recusado (informar todos ou nenhum);
- configuração sem `cTribNac` e certificado sem CNPJ recusam antes de montar XML;
- recuperação após timeout ambíguo: sem chave não inventa nota; falha ao baixar devolve `None`.

Sem rede e sem banco: sessão, certificado e cliente são dublês.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.db.models.enums import AmbienteFiscal, StatusFatura
from app.db.models.invoice import Invoice
from app.nfse import servico
from app.nfse.errors import ErroSefin, TipoErroFiscal

TENANT = SimpleNamespace(id=uuid.uuid4())
CONF = SimpleNamespace(sefin_base_url="", sefin_permitir_host_nao_oficial=False)


class ResultadoFalso:
    def __init__(self, itens: list) -> None:
        self._itens = itens

    def scalars(self) -> ResultadoFalso:
        return self

    def first(self):
        return self._itens[0] if self._itens else None

    def all(self) -> list:
        return self._itens


class SessaoFalsa:
    def __init__(self, itens: list | None = None) -> None:
        self._itens = itens or []
        self.adicionados: list = []
        self.flushes = 0

    def add(self, objeto: object) -> None:
        self.adicionados.append(objeto)

    async def flush(self) -> None:
        self.flushes += 1

    async def execute(self, consulta: object) -> ResultadoFalso:
        return ResultadoFalso(self._itens)


def _config(**extra) -> SimpleNamespace:
    base = dict(
        id=uuid.uuid4(),
        tenant_id=TENANT.id,
        ambiente=AmbienteFiscal.HOMOLOGACAO,
        municipio_ibge="5200258",
        codigo_tributacao_nacional="010701",
        aliquota_iss=Decimal("0.05"),
        serie_dps=1,
        proximo_numero_dps=1,
        optante_mei=False,
        simples_nacional=False,
        inscricao_municipal=None,
        extra={},
    )
    base.update(extra)
    return SimpleNamespace(**base)


def _invoice() -> Invoice:
    return Invoice(
        id=uuid.uuid4(),
        tenant_id=TENANT.id,
        idempotency_key="k1",
        status=StatusFatura.PENDENTE,
        valor_servico="10.00",
        descricao_servico="servico",
        competencia="2026-11",
    )


class TestConfigDoTenant:
    async def test_sem_configuracao_recusa(self) -> None:
        with pytest.raises(servico.ConfiguracaoFiscalAusente):
            await servico._config_do_tenant(
                SessaoFalsa([]), TENANT.id, AmbienteFiscal.HOMOLOGACAO, None
            )

    async def test_mais_de_um_municipio_recusa_e_lista(self) -> None:
        """A nota não pode escolher município: com dois cadastros, exige `municipio_ibge`."""
        configs = [_config(municipio_ibge="5200258"), _config(municipio_ibge="3550308")]

        with pytest.raises(servico.ConfiguracaoFiscalAmbigua) as erro:
            await servico._config_do_tenant(
                SessaoFalsa(configs), TENANT.id, AmbienteFiscal.HOMOLOGACAO, None
            )

        assert "5200258" in str(erro.value) and "3550308" in str(erro.value)
        assert "municipio_ibge" in str(erro.value)

    async def test_configuracao_unica_devolve(self) -> None:
        config = _config()

        assert (
            await servico._config_do_tenant(
                SessaoFalsa([config]), TENANT.id, AmbienteFiscal.HOMOLOGACAO, None
            )
            is config
        )


class TestIbscbsDaConfig:
    def test_sem_chaves_devolve_none(self) -> None:
        assert servico._ibscbs_da_config(_config(extra={})) is None

    def test_incompleto_recusa_e_diz_o_que_falta(self) -> None:
        config = _config(extra={"c_ind_op": "100301"})

        with pytest.raises(servico.ConfiguracaoFiscalAusente) as erro:
            servico._ibscbs_da_config(config)

        assert "c_class_trib" in str(erro.value)
        assert "todos ou nenhum" in str(erro.value)

    def test_completo_monta_ibscbs(self) -> None:
        config = _config(
            extra={
                "c_ind_op": "100301",
                "c_class_trib": "000001",
                "c_nbs": "123456789",
                "tp_oper": "1",
            }
        )

        ibs = servico._ibscbs_da_config(config)

        assert ibs is not None
        assert ibs.c_ind_op == "100301"
        assert ibs.ind_final == "1"
        assert ibs.tp_oper == "1"


class TestMontarEntrada:
    def test_sem_codigo_tributacao_recusa(self) -> None:
        with pytest.raises(servico.ConfiguracaoFiscalAusente) as erro:
            servico._montar_entrada(
                invoice=_invoice(),
                config=_config(codigo_tributacao_nacional=None),
                numero_dps=1,
                certificado_cnpj="64339333000122",
                settings=CONF,
            )

        assert "cTribNac" in str(erro.value)

    def test_sem_documento_do_prestador_recusa(self) -> None:
        with pytest.raises(servico.CertificadoAusente) as erro:
            servico._montar_entrada(
                invoice=_invoice(),
                config=_config(),
                numero_dps=1,
                certificado_cnpj="",
                settings=CONF,
            )

        assert "CNPJ do prestador" in str(erro.value)

    def test_configuracao_valida_monta_entrada(self) -> None:
        entrada = servico._montar_entrada(
            invoice=_invoice(),
            config=_config(),
            numero_dps=1,
            certificado_cnpj="64339333000122",
            settings=CONF,
        )

        assert entrada.prestador.documento == "64339333000122"
        assert entrada.c_mun_emissor == "5200258"
        assert entrada.valor == Decimal("10.00")


class TestTentarRecuperar:
    async def test_sem_chave_devolve_none(self) -> None:
        class Cliente:
            def consultar_dps(self, id_dps):
                return None

        erro = ErroSefin(TipoErroFiscal.AMBIGUO, "timeout")

        assert await servico._tentar_recuperar(Cliente(), "DPS1", erro) is None

    async def test_chave_sem_nfse_devolve_none(self) -> None:
        class Cliente:
            def consultar_dps(self, id_dps):
                return "chave"

            def consultar_nfse(self, chave):
                raise ErroSefin(TipoErroFiscal.INDISPONIVEL, "adn fora")

        erro = ErroSefin(TipoErroFiscal.AMBIGUO, "timeout")

        assert await servico._tentar_recuperar(Cliente(), "DPS1", erro) is None

    async def test_chave_com_nfse_devolve_resposta(self) -> None:
        resposta = SimpleNamespace(chave_acesso="chave")

        class Cliente:
            def consultar_dps(self, id_dps):
                return "chave"

            def consultar_nfse(self, chave):
                return resposta

        erro = ErroSefin(TipoErroFiscal.AMBIGUO, "timeout")

        assert await servico._tentar_recuperar(Cliente(), "DPS1", erro) is resposta


class TestAliquotaEmPercentual:
    def test_none_continua_none(self) -> None:
        assert servico._aliquota_em_percentual(None) is None

    def test_fracao_vira_percentual(self) -> None:
        assert servico._aliquota_em_percentual(Decimal("0.05")) == Decimal("5")
