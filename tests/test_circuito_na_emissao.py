"""Circuit breaker integrado ao fluxo de emissão: bloqueia e responde 503."""

from __future__ import annotations

from app.nfse.injecao import UF_NACIONAL, chave_da_emissao, emitir_com_circuito
from app.nfse.resiliencia import registro_padrao


class TestRotaUsaCircuito:
    def test_chave_da_emissao_e_a_nacional(self) -> None:
        # NFS-e hoje é só padrão nacional: um circuito cobre todos os municípios.
        assert chave_da_emissao(UF_NACIONAL) == "sefaz:NACIONAL:autorizacao"

    def test_circuito_aparece_na_observabilidade_apos_uso(self) -> None:
        from app.core.circuit import Estado

        registro_padrao.resetar()
        registro_padrao.obter(chave_da_emissao(UF_NACIONAL))
        reportado = registro_padrao.estados()[chave_da_emissao(UF_NACIONAL)]
        assert reportado == Estado.FECHADO
        registro_padrao.resetar()


class TestRespostaQuandoAberto:
    async def test_503_com_retry_after(self, app_teste) -> None:
        from app.core.circuit import CircuitoAberto

        # Simula o handler sem depender de emissão real: o circuito aberto precisa
        # responder 503 com orientação, não 500 genérico.
        problema = CircuitoAberto(30.0)
        resposta = await app_teste.exception_handlers[CircuitoAberto](None, problema)
        assert resposta.status_code == 503
        assert resposta.headers["Retry-After"] == "30"
        assert resposta.headers["content-type"].startswith("application/problem+json")

    async def test_corpo_explica_o_que_fazer(self, app_teste) -> None:
        import json

        from app.core.circuit import CircuitoAberto

        problema = CircuitoAberto(15.0)
        resposta = await app_teste.exception_handlers[CircuitoAberto](None, problema)
        corpo = json.loads(resposta.body)
        assert corpo["retryable"] is True
        assert corpo["origem"] == "SEFAZ"
        assert "15s" in corpo["detail"]


class TestBloqueio:
    async def test_circuito_aberto_impede_a_chamada(self) -> None:
        registro_padrao.resetar()
        chave = chave_da_emissao(UF_NACIONAL)
        circuito = registro_padrao.obter(chave)
        for _ in range(circuito.limite_falhas):
            circuito.registrar_falha()

        chamou = False

        async def nao_devia():
            nonlocal chamou
            chamou = True
            return "x"

        import contextlib

        from app.core.circuit import CircuitoAberto

        with contextlib.suppress(CircuitoAberto):
            await emitir_com_circuito(registro_padrao, uf=UF_NACIONAL, acao=nao_devia)
        assert chamou is False, "com circuito aberto a SEFIN não pode ser chamada"
        registro_padrao.resetar()


class TestCancelamentoEEventoUsamCircuito:
    """Cancelamento e evento falam com a **mesma** SEFIN e agora têm circuito próprio.

    Antes só a emissão tinha: com a SEFIN fora, cada cancelamento e cada evento queimava
    timeout próprio. As chaves são separadas por operação de propósito — uma rejeição de
    cancelamento não pode abrir o circuito de emissão.
    """

    def test_chaves_sao_distintas_por_operacao(self) -> None:
        from app.nfse.injecao import (
            OPERACAO_CANCELAMENTO,
            OPERACAO_EMISSAO,
            OPERACAO_EVENTO,
            UF_NACIONAL,
        )
        from app.nfse.resiliencia import chave_sefaz

        chaves = {
            chave_sefaz(UF_NACIONAL, OPERACAO_EMISSAO),
            chave_sefaz(UF_NACIONAL, OPERACAO_CANCELAMENTO),
            chave_sefaz(UF_NACIONAL, OPERACAO_EVENTO),
        }
        assert len(chaves) == 3

    async def test_circuito_aberto_impede_cancelamento(self) -> None:
        import contextlib

        from app.core.circuit import CircuitoAberto
        from app.nfse.injecao import OPERACAO_CANCELAMENTO, UF_NACIONAL, executar_com_circuito
        from app.nfse.resiliencia import chave_sefaz, registro_padrao

        registro_padrao.resetar()
        circuito = registro_padrao.obter(chave_sefaz(UF_NACIONAL, OPERACAO_CANCELAMENTO))
        for _ in range(circuito.limite_falhas):
            circuito.registrar_falha()

        chamou = False

        async def nao_devia():
            nonlocal chamou
            chamou = True
            return "x"

        with contextlib.suppress(CircuitoAberto):
            await executar_com_circuito(
                registro_padrao,
                uf=UF_NACIONAL,
                operacao=OPERACAO_CANCELAMENTO,
                acao=nao_devia,
            )

        assert chamou is False, "com o circuito aberto o cancelamento nao pode ir a SEFIN"
        registro_padrao.resetar()

    async def test_circuito_aberto_impede_evento(self) -> None:
        import contextlib

        from app.core.circuit import CircuitoAberto
        from app.nfse.injecao import OPERACAO_EVENTO, UF_NACIONAL, executar_com_circuito
        from app.nfse.resiliencia import chave_sefaz, registro_padrao

        registro_padrao.resetar()
        circuito = registro_padrao.obter(chave_sefaz(UF_NACIONAL, OPERACAO_EVENTO))
        for _ in range(circuito.limite_falhas):
            circuito.registrar_falha()

        chamou = False

        async def nao_devia():
            nonlocal chamou
            chamou = True
            return "x"

        with contextlib.suppress(CircuitoAberto):
            await executar_com_circuito(
                registro_padrao,
                uf=UF_NACIONAL,
                operacao=OPERACAO_EVENTO,
                acao=nao_devia,
            )

        assert chamou is False, "com o circuito aberto o evento nao pode ir a SEFIN"
        registro_padrao.resetar()

    def test_estado_do_registro_e_por_processo(self) -> None:
        """Documenta o limite: dois registros não compartilham estado.

        Com N processos, cada um tem seu contador — o limite efetivo é N x `limite_falhas`.
        Compartilhar exigiria Redis (dependência já presente) e é decisão registrada em §47.
        """
        from app.nfse.resiliencia import RegistroCircuitos, chave_sefaz

        um, outro = RegistroCircuitos(), RegistroCircuitos()
        chave = chave_sefaz(UF_NACIONAL, "autorizacao")
        for _ in range(um.obter(chave).limite_falhas):
            um.obter(chave).registrar_falha()

        assert um.estados()[chave] == "aberto"
        assert outro.estados() == {}, (
            "registro novo nao herda estado: com N processos cada um conta sozinho"
        )
