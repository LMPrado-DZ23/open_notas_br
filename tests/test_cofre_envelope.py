"""Cofre do certificado: envelope selado, recusas e extração de CNPJ.

O `abrir_pfx` desmonta um envelope montado por `selar_pfx`. Ele precisa recusar — e não estourar — três
corrupções possíveis: corpo curto demais, tamanho declarado maior que o corpo e tamanho zero. Cada uma
é um caminho de erro real de backup/restauração mal feita.
"""

from __future__ import annotations

import uuid

import pytest
from app.certificates.cofre import (
    CertificadoA1,
    ErroCertificado,
    abrir_pfx,
    selar_pfx,
)

CHAVE = b"k" * 32  # Cofre espera 32 bytes crus (AES-256), não base64
TENANT = uuid.uuid4()
PFX = b"\x30\x82simulado"


class TestEnvelope:
    def test_ida_e_volta_sem_senha(self) -> None:
        envelope = selar_pfx(PFX, tenant_id=TENANT, chave=CHAVE)

        pfx, senha = abrir_pfx(envelope, tenant_id=TENANT, chave=CHAVE)

        assert pfx == PFX
        assert senha is None

    def test_ida_e_volta_com_senha(self) -> None:
        envelope = selar_pfx(PFX, tenant_id=TENANT, chave=CHAVE, senha=b"segredo")

        pfx, senha = abrir_pfx(envelope, tenant_id=TENANT, chave=CHAVE, tem_senha=True)

        assert pfx == PFX
        assert senha == b"segredo"

    def test_envelope_de_outro_tenant_nao_abre(self) -> None:
        envelope = selar_pfx(PFX, tenant_id=TENANT, chave=CHAVE)

        from app.core.crypto import ErroDeCriptografia

        with pytest.raises(ErroDeCriptografia):
            abrir_pfx(envelope, tenant_id=uuid.uuid4(), chave=CHAVE)

    def test_envelope_truncado_recusa(self, monkeypatch) -> None:
        """Corpo com menos de 4 bytes não tem cabeçalho de tamanho."""
        envelope = selar_pfx(b"", tenant_id=TENANT, chave=CHAVE)

        with pytest.raises(ErroCertificado) as erro:
            abrir_pfx(envelope, tenant_id=TENANT, chave=CHAVE)

        assert "truncado" in str(erro.value) or "inconsistente" in str(erro.value)

    def test_tamanho_declarado_maior_que_o_corpo_recusa(self) -> None:
        from app.core.crypto import Cofre, aad_do_tenant

        # Cabeçalho diz 999 bytes, mas o corpo não tem isso.
        corpo = (999).to_bytes(4, "big") + b"curto"
        envelope = Cofre(CHAVE).selar(corpo, aad=aad_do_tenant(TENANT))

        with pytest.raises(ErroCertificado) as erro:
            abrir_pfx(envelope, tenant_id=TENANT, chave=CHAVE)

        assert "inconsistente" in str(erro.value)

    def test_tamanho_zero_recusa(self) -> None:
        from app.core.crypto import Cofre, aad_do_tenant

        corpo = (0).to_bytes(4, "big") + b"resto"
        envelope = Cofre(CHAVE).selar(corpo, aad=aad_do_tenant(TENANT))

        with pytest.raises(ErroCertificado) as erro:
            abrir_pfx(envelope, tenant_id=TENANT, chave=CHAVE)

        assert "inconsistente" in str(erro.value)


class TestDePfx:
    def test_pfx_vazio_recusa(self) -> None:
        with pytest.raises(ErroCertificado) as erro:
            CertificadoA1.de_pfx(b"")

        assert "vazio" in str(erro.value)

    def test_conteudo_que_nao_e_pkcs12_recusa(self) -> None:
        with pytest.raises(ErroCertificado) as erro:
            CertificadoA1.de_pfx(b"nao-e-um-pfx", "senha")

        assert "senha incorreta" in str(erro.value)

    def test_pfx_real_sem_senha_abre(self) -> None:
        """Mesmo caminho da emissão: PFX gerado no teste, aberto pelo cofre."""
        from tests.test_fase2_certificado import SENHA, gerar_pfx

        certificado = CertificadoA1.de_pfx(gerar_pfx(), SENHA.decode())

        assert certificado.cnpj == "11222333000181"
        assert certificado.valido_ate is not None
        chave_pem, _cadeia = certificado.material_para_assinatura()
        assert str(chave_pem).startswith("-----BEGIN")
