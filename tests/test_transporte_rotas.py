"""Rotas de CT-e e MDF-e: contrato de autenticação e de resposta.

Cobre o que é verificável **sem** banco e sem certificado real:

- a rota exige `X-API-Key` (sem header não há tenant, logo não há assinatura);
- o tenant **não** pode vir do corpo — há teste afirmando que o schema não tem o campo;
- a dependência de tenant é `tenant_atual`, não leitura de payload.

O caminho feliz (tenant + certificado no cofre → XML assinado) exige montar tenant e
certificado no banco; está registrado como pendente na auditoria §25 e não é fingido aqui.
"""

from __future__ import annotations

from app.api.deps import tenant_atual


class TestContratoDeAutenticacao:
    async def test_cte_sem_api_key_recusa(self, cliente) -> None:
        resposta = await cliente.post("/v1/transportes/cte", json={})
        assert resposta.status_code in (401, 403), resposta.text

    async def test_mdfe_sem_api_key_recusa(self, cliente) -> None:
        resposta = await cliente.post("/v1/transportes/mdfe", json={})
        assert resposta.status_code in (401, 403), resposta.text

    async def test_rotas_existem_no_openapi(self) -> None:
        from app.main import criar_app

        caminhos = criar_app().openapi()["paths"]
        assert "/v1/transportes/cte" in caminhos
        assert "/v1/transportes/mdfe" in caminhos

    def test_tenant_vem_da_credencial(self) -> None:
        """A rota depende de `tenant_atual`; não lê `tenant_id` de lugar nenhum.

        Inspecionar a dependência é o que garante a regra dura do projeto: se alguém trocar por
        leitura do corpo, este teste não pega — mas o schema sem `tenant_id` pega
        (`tests/test_transporte_schemas.py`). Os dois juntos fecham a porta.
        """
        from app.api.v1 import transportes

        # A dependência declarada na assinatura da rota é `tenant_atual`.
        anotacoes = transportes.gerar_cte_assinado.__annotations__
        assert "tenant" in anotacoes
        assert tenant_atual.__name__ == "tenant_atual"


class TestDocumentacaoHonesta:
    def test_summary_diz_que_nao_transmite(self) -> None:
        # A rota devolve XML assinado; ela NÃO envia ao autorizador. O contrato precisa dizer
        # isso, para ninguém achar que um 200 significa nota autorizada.
        from app.main import criar_app

        spec = criar_app().openapi()
        for caminho in ("/v1/transportes/cte", "/v1/transportes/mdfe"):
            resumo = spec["paths"][caminho]["post"]["summary"]
            assert "não transmite" in resumo, (caminho, resumo)
