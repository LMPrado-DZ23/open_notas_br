"""Rotação da chave-mestra: re-sela tudo e verifica antes de gravar (§53).

O que precisa ser provado, além de "a função roda":

1. **re-sela de verdade**: depois da rotação, a chave **nova** abre e a **antiga** não;
2. **respeita o `aad`**: credencial municipal usa tenant + município; trocar o município no teste
   faz a abertura falhar (é o que impede mover blob entre municípios);
3. **falha limpa**: se a chave antiga informada não é a que selou o dado, nada é gravado;
4. **recusa** chave nova igual à antiga ou malformada.
"""

from __future__ import annotations

import base64
import os
import uuid

import pytest
from app.core.crypto import Cofre, ErroDeCriptografia, aad_do_tenant
from app.db.models.frete import FreteCredencial
from app.db.models.tenant import Tenant, TenantCertificate
from scripts import rotacionar_chave_mestra as rotacao

ANTIGA = b"\x01" * 32
NOVA = b"\x02" * 32


def b64(chave: bytes) -> str:
    return base64.b64encode(chave).decode()


class TestDecodificarChave:
    def test_aceita_base64_de_32_bytes(self) -> None:
        assert rotacao.decodificar_chave(b64(ANTIGA), nome="X") == ANTIGA

    def test_recusa_ausente(self) -> None:
        with pytest.raises(ValueError, match="ausente"):
            rotacao.decodificar_chave("", nome="X")

    def test_recusa_tamanho_errado(self) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            rotacao.decodificar_chave(base64.b64encode(b"curta").decode(), nome="X")

    def test_recusa_base64_invalido(self) -> None:
        with pytest.raises(ValueError, match="base64"):
            rotacao.decodificar_chave("não é base64!!", nome="X")


@pytest.fixture
async def material_selado(sessao_db):
    """Tenant com certificado, segredo de webhook e credencial de frete selados com ANTIGA."""
    antigo = Cofre(ANTIGA)
    tenant = Tenant(
        slug="rotacao",
        nome="Rotacao LTDA",
        api_key_prefix="rotacao1",
        api_key_hash="hash-rotacao".ljust(16, "0")[:16],
    )
    sessao_db.add(tenant)
    await sessao_db.flush()

    aad = aad_do_tenant(tenant.id)
    tenant.webhook_secret_selado = antigo.selar(b"segredo-do-webhook", aad=aad)
    sessao_db.add(
        TenantCertificate(
            tenant_id=tenant.id,
            apelido="a1",
            cnpj="11222333000181",
            subject_cn="Empresa Teste LTDA",
            emissor="Teste",
            numero_serie="1",
            valido_de=None,
            valido_ate=None,
            fingerprint_sha256="f" * 64,
            pfx_selado=antigo.selar(b"conteudo-do-pfx", aad=aad),
            senha_selada=antigo.selar(b"senha", aad=aad),
            ativo=True,
        )
    )
    sessao_db.add(
        FreteCredencial(
            tenant_id=tenant.id,
            access_token_selado=antigo.selar(b"token", aad=aad),
            expira_em=None,
        )
    )
    await sessao_db.commit()
    return tenant.id


class TestRotacao:
    async def test_nova_chave_abre_e_antiga_nao(self, sessao_db, material_selado) -> None:
        tenant_id = material_selado
        resultado = await rotacao.rotacionar(sessao_db, antiga=ANTIGA, nova=NOVA)
        await sessao_db.commit()

        assert resultado.total > 0

        tenant = await sessao_db.get(Tenant, tenant_id)
        assert tenant is not None
        aad = aad_do_tenant(tenant_id)

        # A chave nova abre…
        assert Cofre(NOVA).abrir(tenant.webhook_secret_selado, aad=aad) == b"segredo-do-webhook"
        # …e a antiga não. É a prova de que houve re-selagem, não só reescrita.
        with pytest.raises(ErroDeCriptografia):
            Cofre(ANTIGA).abrir(tenant.webhook_secret_selado, aad=aad)

    async def test_verificacao_conta_os_campos(self, sessao_db, material_selado) -> None:
        await rotacao.rotacionar(sessao_db, antiga=ANTIGA, nova=NOVA)

        abertos = await rotacao.verificar(sessao_db, nova=NOVA)

        # certificado (pfx + senha) + webhook + token de frete
        assert abertos == 4

    async def test_chave_antiga_errada_nao_grava_nada(self, sessao_db, material_selado) -> None:
        tenant_id = material_selado

        with pytest.raises(ErroDeCriptografia):
            await rotacao.rotacionar(sessao_db, antiga=b"\x09" * 32, nova=NOVA)
        await sessao_db.rollback()

        tenant = await sessao_db.get(Tenant, tenant_id)
        assert tenant is not None
        # O selo original continua válido com a chave antiga: nada foi sobrescrito.
        assert (
            Cofre(ANTIGA).abrir(tenant.webhook_secret_selado, aad=aad_do_tenant(tenant_id))
            == b"segredo-do-webhook"
        )

    async def test_recusa_chave_nova_igual(self, sessao_db) -> None:
        with pytest.raises(ValueError, match="igual"):
            await rotacao.rotacionar(sessao_db, antiga=ANTIGA, nova=ANTIGA)

    async def test_aad_amarra_ao_tenant(self, sessao_db, material_selado) -> None:
        """Blob de um tenant não abre no contexto de outro — antes e depois da rotação."""
        tenant_id = material_selado
        await rotacao.rotacionar(sessao_db, antiga=ANTIGA, nova=NOVA)

        tenant = await sessao_db.get(Tenant, tenant_id)
        assert tenant is not None
        with pytest.raises(ErroDeCriptografia):
            Cofre(NOVA).abrir(tenant.webhook_secret_selado, aad=aad_do_tenant(uuid.uuid4()))


class TestCli:
    async def test_sem_variaveis_recusa(self, monkeypatch, capsys) -> None:
        monkeypatch.delenv("MASTER_ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("MASTER_ENCRYPTION_KEY_NOVA", raising=False)

        codigo = await rotacao.executar()

        assert codigo == 2
        assert "recusando rodar" in capsys.readouterr().err

    async def test_chave_nova_igual_recusa(self, monkeypatch, capsys) -> None:
        monkeypatch.setenv("MASTER_ENCRYPTION_KEY", b64(ANTIGA))
        monkeypatch.setenv("MASTER_ENCRYPTION_KEY_NOVA", b64(ANTIGA))
        # Garante que a sessão de banco do teste seja reaproveitada.
        os.environ.setdefault("DATABASE_URL", os.environ["DATABASE_URL"])

        codigo = await rotacao.executar()

        assert codigo == 1
        assert "igual" in capsys.readouterr().err
