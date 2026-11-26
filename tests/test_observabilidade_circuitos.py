"""Rota de circuitos: contrato, código numérico e ausência de dado sensível."""

from __future__ import annotations

from app.nfse.resiliencia import chave_sefaz, registro_padrao


class TestContrato:
    async def test_lista_vazia_traz_observacao(self, cliente) -> None:
        # Ausência de circuito significa "nada foi chamado", não "tudo saudável".
        registro_padrao.resetar()
        resposta = await cliente.get("/v1/health/circuitos")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert "circuitos" in corpo
        assert "não que todos estejam saudáveis" in corpo["observacao"]

    async def test_circuito_aberto_aparece_com_codigo_2(self, cliente) -> None:
        registro_padrao.resetar()
        circuito = registro_padrao.obter(chave_sefaz("GO", "autorizacao"))
        for _ in range(circuito.limite_falhas):
            circuito.registrar_falha()

        corpo = (await cliente.get("/v1/health/circuitos")).json()
        go = next(c for c in corpo["circuitos"] if c["nome"] == chave_sefaz("GO", "autorizacao"))
        assert go["estado"] == "aberto"
        assert go["codigo"] == 2
        registro_padrao.resetar()

    async def test_circuito_fechado_codigo_0(self, cliente) -> None:
        registro_padrao.resetar()
        registro_padrao.obter(chave_sefaz("SP", "status"))
        corpo = (await cliente.get("/v1/health/circuitos")).json()
        sp = next(c for c in corpo["circuitos"] if c["nome"] == chave_sefaz("SP", "status"))
        assert sp["codigo"] == 0

    async def test_nao_exige_autenticacao(self, cliente) -> None:
        # Estado de saúde de infraestrutura, não dado de tenant.
        assert (await cliente.get("/v1/health/circuitos")).status_code == 200

    async def test_nao_vaza_nada_de_tenant(self, cliente) -> None:
        corpo = (await cliente.get("/v1/health/circuitos")).json()
        texto = str(corpo)
        assert "api_key" not in texto.lower()
        assert "tenant_id" not in texto.lower()
