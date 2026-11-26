"""Raízes do sistema no contexto TLS: o que destrava SVRS e SEFAZ-SP.

Motivo medido (auditoria §28): com `ssl.create_default_context()` apenas, o handshake contra
`nfe-homologacao.svrs.rs.gov.br` falhava com `CERTIFICATE_VERIFY_FAILED — unable to get local
issuer certificate`. A cadeia sobe para raízes ICP-Brasil que não estão no bundle do OpenSSL.
"""

from __future__ import annotations

import ssl

from app.certificates.cofre import CertificadoA1, _carregar_raizes_do_sistema


class TestRaizesDoSistema:
    def test_nao_explode_em_plataforma_sem_loja(self) -> None:
        # Em Linux não existe `ssl.enum_certificates`; a função precisa ser inerte, não falhar.
        ctx = ssl.create_default_context()
        assert isinstance(_carregar_raizes_do_sistema(ctx), int)

    def test_ssl_context_do_certificado_continua_valido(self) -> None:
        from tests.test_fase2_certificado import SENHA, gerar_pfx

        cert = CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())
        ctx = cert.ssl_context()
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2

    def test_raizes_sao_carregaveis_quando_a_loja_existe(self) -> None:
        # Só roda onde há loja (Windows). Em CI Linux é pulado, e isso é honesto: o que se testa
        # aqui é a importação das raízes do SO, que não existe naquele ambiente.
        if not hasattr(ssl, "enum_certificates"):
            import pytest

            pytest.skip("plataforma sem ssl.enum_certificates (Linux)")
        ctx = ssl.create_default_context()
        assert _carregar_raizes_do_sistema(ctx) > 0
