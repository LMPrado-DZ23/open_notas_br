"""Testes de credencial e assinatura de webhook."""

from __future__ import annotations

from app.core.security import (
    PREFIXO_API_KEY,
    assinar_webhook,
    gerar_api_key,
    gerar_segredo_webhook,
    hash_api_key,
    hashs_iguais,
    verificar_assinatura_webhook,
)


class TestApiKey:
    def test_formato(self) -> None:
        completa, prefixo, _ = gerar_api_key()
        assert completa.startswith(PREFIXO_API_KEY)
        assert prefixo == completa[: len(PREFIXO_API_KEY) + 8]
        assert prefixo != completa, "prefixo não pode ser a chave inteira"

    def test_hash_corresponde_e_nao_e_reversivel(self) -> None:
        completa, _, hash_ = gerar_api_key()
        assert hash_ == hash_api_key(completa)
        assert completa not in hash_
        assert len(hash_) == 64

    def test_hash_e_deterministico(self) -> None:
        assert hash_api_key("nb_abc") == hash_api_key("nb_abc")

    def test_chaves_distintas(self) -> None:
        chaves = {gerar_api_key()[0] for _ in range(50)}
        assert len(chaves) == 50

    def test_hashs_iguais_em_tempo_constante(self) -> None:
        assert hashs_iguais("abc", "abc") is True
        assert hashs_iguais("abc", "abd") is False


class TestWebhook:
    def test_assinatura_ida_e_volta(self) -> None:
        segredo = gerar_segredo_webhook().encode()
        corpo = b'{"evento":"nfse.autorizada"}'
        assinatura = assinar_webhook(corpo, segredo)
        assert verificar_assinatura_webhook(corpo, segredo, assinatura) is True

    def test_corpo_alterado_invalida(self) -> None:
        segredo = b"segredo"
        assinatura = assinar_webhook(b"original", segredo)
        assert verificar_assinatura_webhook(b"adulterado", segredo, assinatura) is False

    def test_segredo_errado_invalida(self) -> None:
        assinatura = assinar_webhook(b"corpo", b"segredo-a")
        assert verificar_assinatura_webhook(b"corpo", b"segredo-b", assinatura) is False

    def test_assinatura_ausente_invalida(self) -> None:
        assert verificar_assinatura_webhook(b"corpo", b"s", "") is False

    def test_assinatura_aceita_maiuscula(self) -> None:
        segredo = b"segredo"
        corpo = b"corpo"
        assinatura = assinar_webhook(corpo, segredo)
        assert verificar_assinatura_webhook(corpo, segredo, assinatura.upper()) is True

    def test_segredo_tem_entropia_suficiente(self) -> None:
        segredo = gerar_segredo_webhook()
        assert len(segredo) == 64
        assert int(segredo, 16) > 0
