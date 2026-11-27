class TestValidacaoProblemJson:
    """422 também é problem+json, sem perder o `detail` que o cliente já lê (§69).

    Medido antes da correção: 401/404/405 saíam `application/problem+json` e o 422 saía
    `application/json` (handler padrão do FastAPI). O cliente tinha de tratar dois formatos.
    """

    async def test_422_tem_content_type_problem_json(self, cliente) -> None:
        resposta = await cliente.post("/v1/tenants", json={"slug": "x"})

        assert resposta.status_code == 422
        assert resposta.headers["content-type"].startswith("application/problem+json")

    async def test_422_tem_campos_rfc7807(self, cliente) -> None:
        corpo = (await cliente.post("/v1/tenants", json={"slug": "x"})).json()

        assert corpo["status"] == 422
        assert corpo["title"] == "Requisição inválida"
        assert corpo["type"].endswith("/validacao")
        assert "retryable" in corpo and "origem" in corpo

    async def test_422_preserva_detail_como_lista(self, cliente) -> None:
        """Contrato antigo: `detail` era a lista de erros do Pydantic. Continua sendo."""
        corpo = (await cliente.post("/v1/tenants", json={"slug": "x"})).json()

        assert isinstance(corpo["detail"], list)
        assert corpo["detail"], "lista vazia esconde o motivo da recusa"
        assert {"loc", "msg", "type"} <= set(corpo["detail"][0])

    async def test_422_erros_espelham_detail(self, cliente) -> None:
        corpo = (await cliente.post("/v1/tenants", json={"slug": "x"})).json()

        assert corpo["errors"] == corpo["detail"]

    async def test_erro_de_http_exception_continua_problem_json(self, cliente) -> None:
        """Contraprova: o handler novo não pode ter roubado o caminho do HTTPException."""
        resposta = await cliente.get("/v1/me/config-fiscal")

        assert resposta.status_code == 401
        assert resposta.headers["content-type"].startswith("application/problem+json")
