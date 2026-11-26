"""Status de transporte na API: auth, catálogo e recusas."""

from __future__ import annotations

import pytest


class TestContrato:
    async def test_sem_api_key_recusa(self, cliente) -> None:
        resposta = await cliente.get("/v1/transportes/status?documento=cte&uf=ES")
        assert resposta.status_code in (401, 403), resposta.text

    def test_rota_existe_no_openapi(self) -> None:
        from app.main import criar_app

        assert "/v1/transportes/status" in criar_app().openapi()["paths"]

    def test_summary_diz_que_nao_emite(self) -> None:
        from app.main import criar_app

        resumo = criar_app().openapi()["paths"]["/v1/transportes/status"]["get"]["summary"]
        assert "não emite" in resumo

    def test_uf_desconhecida_vira_422(self) -> None:
        # A auth roda antes da validação de query, então o 422 de UF é testado na função que o
        # produz — sem depender de tenant no banco.
        from app.api.v1.transportes_status import _cuf
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            _cuf("XX")
        assert exc.value.status_code == 422

    def test_uf_conhecida_vira_codigo_ibge(self) -> None:
        from app.api.v1.transportes_status import _cuf

        assert _cuf("ES") == "32"
        assert _cuf("go") == "52"
