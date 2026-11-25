"""Testes de lote: leitura de CSV, processamento e relatório.

O critério é o que o usuário vê: para N linhas enviadas, quantas viraram nota,
quais não viraram e por quê. Lote que "termina sem erro" mas perde linha é pior
que lote que falha alto.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from app.batches.csv import CsvInvalido, ler_csv
from app.core.config import Settings, get_settings
from sqlalchemy import select

from tests.test_fase2_certificado import SENHA, gerar_pfx

CABECALHO = "idempotency_key,valor,descricao,competencia,tomador_nome,tomador_documento"


def csv_de(*linhas: str) -> bytes:
    return ("\n".join([CABECALHO, *linhas]) + "\n").encode("utf-8")


@pytest.fixture
async def tenant(cliente) -> dict[str, Any]:
    resposta = await cliente.post("/v1/tenants", json={"slug": "lote-tenant", "nome": "Lote LTDA"})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def cabecalho(tenant: dict[str, Any]) -> dict[str, str]:
    return {"X-API-Key": tenant["api_key"]}


class TestLeituraCsv:
    def test_le_linhas_validas(self) -> None:
        lote = ler_csv(csv_de("chave-001,100.00,Corte,2026-11,Cliente,11144477735"))
        assert lote.total == 1
        assert len(lote.validas) == 1
        linha = lote.validas[0]
        assert linha.idempotency_key == "chave-001"
        assert linha.valor == Decimal("100.00")
        assert linha.competencia == "2026-11"

    def test_valor_com_virgula_decimal_entre_aspas(self) -> None:
        # Em CSV com vírgula decimal, o campo precisa estar entre aspas.
        lote = ler_csv(csv_de('chave-002,"1.234,56",Serviço,,,'))
        assert lote.validas[0].valor == Decimal("1234.56")

    def test_valor_sem_aspas_e_recusado(self) -> None:
        # Sem aspas o CSV corta o campo: `valor` vira "1.234" e a descrição "56".
        # Precisa falhar alto em vez de emitir nota com valor errado.
        lote = ler_csv(csv_de("chave-0021,1.234,56,Serviço,,"))
        assert lote.invalidas, "linha malformada deve ser recusada"
        assert "casas decimais" in (lote.invalidas[0].erro or "")

    def test_cabecalho_obrigatorio(self) -> None:
        with pytest.raises(CsvInvalido, match="cabeçalho"):
            ler_csv(b"a,b,c\n1,2,3\n")

    def test_arquivo_vazio(self) -> None:
        with pytest.raises(CsvInvalido):
            ler_csv(b"")

    def test_sem_linhas_de_dados(self) -> None:
        with pytest.raises(CsvInvalido, match="nenhuma linha"):
            ler_csv(CABECALHO.encode("utf-8"))

    def test_linha_invalida_nao_derruba_lote(self) -> None:
        lote = ler_csv(
            csv_de(
                "chave-ok1,100.00,Corte,,,",
                "curta,50.00,Serviço,,,",
                "chave-ok2,70.00,Barba,,,",
            )
        )
        assert lote.total == 3
        assert len(lote.validas) == 2
        assert len(lote.invalidas) == 1
        assert "8 caracteres" in (lote.invalidas[0].erro or "")

    def test_valor_invalido(self) -> None:
        lote = ler_csv(csv_de("chave-003,abc,Serviço,,,"))
        assert "valor" in (lote.invalidas[0].erro or "")

    def test_valor_zero(self) -> None:
        lote = ler_csv(csv_de("chave-004,0,Serviço,,,"))
        assert "maior que zero" in (lote.invalidas[0].erro or "")

    def test_descricao_vazia(self) -> None:
        lote = ler_csv(csv_de("chave-005,10.00,,,,"))
        assert "descricao" in (lote.invalidas[0].erro or "")

    def test_competencia_invalida(self) -> None:
        lote = ler_csv(csv_de("chave-006,10.00,Serviço,26-11,,"))
        assert "competência" in (lote.invalidas[0].erro or "")

    def test_chave_repetida_no_arquivo(self) -> None:
        lote = ler_csv(
            csv_de(
                "chave-repetida,10.00,Serviço,,,",
                "chave-repetida,20.00,Outro,,,",
            )
        )
        assert len(lote.validas) == 1
        assert "repetida" in (lote.invalidas[0].erro or "")

    def test_linha_vazia_ignorada(self) -> None:
        lote = ler_csv(csv_de("chave-007,10.00,Serviço,,,", ",,,,,,"))
        assert lote.total == 1

    def test_aceita_cp1252(self) -> None:
        conteudo = (CABECALHO + "\nchave-008,10.00,Manicure,,,\n").encode("cp1252")
        assert ler_csv(conteudo).total == 1

    def test_colunas_extras_sao_ignoradas(self) -> None:
        conteudo = ("idempotency_key,valor,descricao,extra\nchave-009,10.00,Serviço,x\n").encode()
        assert ler_csv(conteudo).validas[0].idempotency_key == "chave-009"


class TestProcessamento:
    async def _preparar(self, cliente, tenant) -> None:
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
            headers=cabecalho(tenant),
        )
        await cliente.post(
            "/v1/me/certificados",
            files={"arquivo": ("c.pfx", gerar_pfx(), "application/x-pkcs12")},
            data={"senha": SENHA.decode(), "apelido": "a1"},
            headers=cabecalho(tenant),
        )

    async def test_processa_n_linhas_com_relatorio(self, cliente, tenant, app_teste) -> None:
        app_teste.dependency_overrides[get_settings] = lambda: Settings(
            environment="test", nfse_adapter="mock"
        )
        try:
            await self._preparar(cliente, tenant)
            conteudo = csv_de(
                "lote-chave-001,100.00,Corte,,,",
                "lote-chave-002,50.00,Barba,,,",
                "curta,25.00,Inválida,,,",
            )
            resposta = await cliente.post(
                "/v1/lotes?processar_agora=true",
                files={"arquivo": ("lote.csv", conteudo, "text/csv")},
                headers=cabecalho(tenant),
            )
            assert resposta.status_code == 200, resposta.text
            corpo = resposta.json()
        finally:
            app_teste.dependency_overrides.clear()

        assert corpo["total_linhas"] == 3
        assert corpo["sucesso"] == 2
        assert corpo["falhas"] == 1
        assert corpo["status"] == "partial"

        relatorio = corpo["relatorio"]
        assert len(relatorio) == 3
        assert [item["status"] for item in relatorio].count("autorizado") == 2
        assert any(item["status"] == "ignorada" for item in relatorio)

    async def test_todas_validas_fica_concluido(self, cliente, tenant, app_teste) -> None:
        app_teste.dependency_overrides[get_settings] = lambda: Settings(
            environment="test", nfse_adapter="mock"
        )
        try:
            await self._preparar(cliente, tenant)
            resposta = await cliente.post(
                "/v1/lotes?processar_agora=true",
                files={
                    "arquivo": (
                        "ok.csv",
                        csv_de("lote2-chave-001,10.00,A,,,", "lote2-chave-002,20.00,B,,,"),
                        "text/csv",
                    )
                },
                headers=cabecalho(tenant),
            )
        finally:
            app_teste.dependency_overrides.clear()

        assert resposta.json()["status"] == "completed"
        assert resposta.json()["falhas"] == 0

    async def test_reprocessar_nao_duplica(self, cliente, tenant, app_teste, sessao_db) -> None:
        from app.db.models.invoice import Invoice

        app_teste.dependency_overrides[get_settings] = lambda: Settings(
            environment="test", nfse_adapter="mock"
        )
        try:
            await self._preparar(cliente, tenant)
            payload = csv_de("lote3-chave-001,30.00,Corte,,,")
            for _ in range(2):
                await cliente.post(
                    "/v1/lotes?processar_agora=true",
                    files={"arquivo": ("dup.csv", payload, "text/csv")},
                    headers=cabecalho(tenant),
                )
        finally:
            app_teste.dependency_overrides.clear()

        resultado = await sessao_db.execute(
            select(Invoice).where(Invoice.idempotency_key == "lote3-chave-001")
        )
        assert len(resultado.scalars().all()) == 1

    async def test_csv_invalido_da_422(self, cliente, tenant) -> None:
        resposta = await cliente.post(
            "/v1/lotes?processar_agora=true",
            files={"arquivo": ("ruim.csv", b"sem,cabecalho\n1,2\n", "text/csv")},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 422

    async def test_listagem_e_detalhe(self, cliente, tenant, app_teste) -> None:
        app_teste.dependency_overrides[get_settings] = lambda: Settings(
            environment="test", nfse_adapter="mock"
        )
        try:
            await self._preparar(cliente, tenant)
            criado = await cliente.post(
                "/v1/lotes?processar_agora=true",
                files={
                    "arquivo": (
                        "lista.csv",
                        csv_de("lote4-chave-001,15.00,Serviço,,,"),
                        "text/csv",
                    )
                },
                headers=cabecalho(tenant),
            )
            lote_id = criado.json()["id"]
        finally:
            app_teste.dependency_overrides.clear()

        listagem = await cliente.get("/v1/lotes", headers=cabecalho(tenant))
        assert listagem.status_code == 200
        assert any(item["id"] == lote_id for item in listagem.json())

        detalhe = await cliente.get(f"/v1/lotes/{lote_id}", headers=cabecalho(tenant))
        assert detalhe.status_code == 200
        assert detalhe.json()["relatorio"]

    async def test_lote_de_outro_tenant_404(self, cliente, tenant, app_teste) -> None:
        app_teste.dependency_overrides[get_settings] = lambda: Settings(
            environment="test", nfse_adapter="mock"
        )
        try:
            await self._preparar(cliente, tenant)
            criado = await cliente.post(
                "/v1/lotes?processar_agora=true",
                files={
                    "arquivo": (
                        "iso.csv",
                        csv_de("lote5-chave-001,10.00,Serviço,,,"),
                        "text/csv",
                    )
                },
                headers=cabecalho(tenant),
            )
        finally:
            app_teste.dependency_overrides.clear()

        outro = await cliente.post("/v1/tenants", json={"slug": "lote-outro", "nome": "Outro LTDA"})
        consulta = await cliente.get(
            f"/v1/lotes/{criado.json()['id']}", headers=cabecalho(outro.json())
        )
        assert consulta.status_code == 404


class TestCriacao:
    async def test_criar_sem_processar_fica_pendente(self, cliente, tenant) -> None:
        resposta = await cliente.post(
            "/v1/lotes",
            files={
                "arquivo": (
                    "pendente.csv",
                    csv_de("lote6-chave-001,10.00,Serviço,,,"),
                    "text/csv",
                )
            },
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["status"] == "pending"
        assert resposta.json()["processadas"] == 0

    async def test_arquivo_grande_recusado(self, cliente, tenant) -> None:
        conteudo = b"x" * (6 * 1024 * 1024)
        resposta = await cliente.post(
            "/v1/lotes",
            files={"arquivo": ("grande.csv", conteudo, "text/csv")},
            headers=cabecalho(tenant),
        )
        assert resposta.status_code == 413
