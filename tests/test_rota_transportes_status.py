"""Consulta de status de CT-e/MDF-e — contrato de recusa e as 27 UFs.

O endpoint é leitura, mas erra de quatro formas distintas, e cada uma manda o cliente fazer outra
coisa: 503 (catálogo sem endpoint para a UF), 422 (sem certificado ativo), 504 (autorizador
inacessível) e 504 (recusa definitiva). Testar só o caminho feliz deixaria as mensagens erradas
passarem — e a mensagem é o que o integrador lê às 3h da manhã.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.api.v1 import transportes_status as rota
from app.nfe.transporte import ErroSefazDefinitivo, ErroTransporte
from fastapi import HTTPException

TENANT = SimpleNamespace(id=uuid.uuid4())
CONF = SimpleNamespace()


class SessaoFalsa:
    def __init__(self, url: str | None = "https://autorizador/x") -> None:
        self._url = url

    async def scalar(self, consulta: object) -> str | None:
        return self._url


class CertificadoFalso:
    def ssl_context(self) -> object:
        return object()


class RespostaFalsa:
    cstat = "107"

    def texto(self, campo: str) -> str:
        return "Servico em operacao"


def _preparar(monkeypatch, *, url="https://autorizador/x", tem_certificado=True, erro=None):
    monkeypatch.setattr(rota, "TransporteHTTP", lambda **k: object())
    monkeypatch.setattr(rota, "ClienteSefaz", lambda transporte, timeout_s: object())

    async def ativo(sessao, tenant_id):
        return SimpleNamespace(id=uuid.uuid4()) if tem_certificado else None

    async def abrir(sessao, registro, **kwargs):
        return CertificadoFalso()

    monkeypatch.setattr(rota.certificados, "ativo", ativo)
    monkeypatch.setattr(rota.certificados, "abrir_para_uso", abrir)

    async def circuito(registro, *, uf, operacao, acao):
        if erro is not None:
            raise erro
        return await acao()

    monkeypatch.setattr(rota, "executar_com_circuito", circuito)

    async def status_cte(sefaz, **kwargs):
        return RespostaFalsa()

    async def status_mdfe(sefaz, **kwargs):
        return RespostaFalsa()

    monkeypatch.setattr(rota.cte_consulta, "consultar_status", status_cte)
    monkeypatch.setattr(rota.mdfe_consulta, "consultar_status", status_mdfe)
    return SessaoFalsa(url)


class TestContratoDeRecusa:
    async def test_sem_endpoint_para_uf_vira_503(self, monkeypatch) -> None:
        sessao = _preparar(monkeypatch, url=None)

        with pytest.raises(HTTPException) as erro:
            await rota.consultar_status_transporte(TENANT, sessao, CONF, "cte", "GO", "2")

        assert erro.value.status_code == 503
        assert "sem endpoint" in erro.value.detail

    async def test_sem_certificado_ativo_vira_422(self, monkeypatch) -> None:
        sessao = _preparar(monkeypatch, tem_certificado=False)

        with pytest.raises(HTTPException) as erro:
            await rota.consultar_status_transporte(TENANT, sessao, CONF, "cte", "SP", "2")

        assert erro.value.status_code == 422
        assert "certificado A1 ativo" in erro.value.detail

    async def test_autorizador_inacessivel_vira_504(self, monkeypatch) -> None:
        sessao = _preparar(monkeypatch, erro=ErroTransporte("timeout"))

        with pytest.raises(HTTPException) as erro:
            await rota.consultar_status_transporte(TENANT, sessao, CONF, "cte", "SP", "2")

        assert erro.value.status_code == 504
        assert "inacessível" in erro.value.detail

    async def test_recusa_definitiva_vira_504_com_motivo(self, monkeypatch) -> None:
        sessao = _preparar(monkeypatch, erro=ErroSefazDefinitivo("rejeicao 999"))

        with pytest.raises(HTTPException) as erro:
            await rota.consultar_status_transporte(TENANT, sessao, CONF, "mdfe", "MT", "1")

        assert erro.value.status_code == 504
        assert "rejeicao 999" in erro.value.detail


class TestCaminhoFeliz:
    @pytest.mark.parametrize("documento", ["cte", "mdfe"])
    async def test_devolve_cstat_e_motivo(self, monkeypatch, documento: str) -> None:
        sessao = _preparar(monkeypatch)

        saida = await rota.consultar_status_transporte(TENANT, sessao, CONF, documento, "sp", "2")

        assert saida == {
            "documento": documento,
            "uf": "SP",  # normalizada em maiúsculas
            "cstat": "107",
            "motivo": "Servico em operacao",
        }

    async def test_circuito_recebe_uf_maiuscula(self, monkeypatch) -> None:
        """Circuito escopado por UF: GO não pode consumir timeout de SP."""
        visto: dict = {}

        async def circuito(registro, *, uf, operacao, acao):
            visto.update({"uf": uf, "operacao": operacao})
            return RespostaFalsa()

        sessao = _preparar(monkeypatch)
        monkeypatch.setattr(rota, "executar_com_circuito", circuito)

        await rota.consultar_status_transporte(TENANT, sessao, CONF, "cte", "go", "2")

        assert visto == {"uf": "GO", "operacao": "consulta_status"}


class TestCuf:
    def test_todas_as_27_ufs_tem_codigo(self) -> None:
        """Reusa a tabela da NF-e; se ela mudar, este teste quebra aqui, não na emissão."""
        ufs = [
            "RO",
            "AC",
            "AM",
            "RR",
            "PA",
            "AP",
            "TO",
            "MA",
            "PI",
            "CE",
            "RN",
            "PB",
            "PE",
            "AL",
            "SE",
            "BA",
            "MG",
            "ES",
            "RJ",
            "SP",
            "PR",
            "SC",
            "RS",
            "MS",
            "MT",
            "GO",
            "DF",
        ]

        codigos = {uf: rota._cuf(uf) for uf in ufs}

        assert len(set(codigos.values())) == 27
        assert codigos["SP"] == "35" and codigos["GO"] == "52" and codigos["DF"] == "53"

    def test_uf_desconhecida_vira_422(self) -> None:
        with pytest.raises(HTTPException) as erro:
            rota._cuf("XX")

        assert erro.value.status_code == 422
        assert "UF desconhecida" in erro.value.detail

    def test_aceita_minuscula(self) -> None:
        assert rota._cuf("sp") == "35"
