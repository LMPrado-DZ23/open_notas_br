"""Credenciais municipais: selo, AAD, numeração e isolamento. Contra Postgres real."""

from __future__ import annotations

import pytest
from app.core.crypto import Cofre, ErroDeCriptografia
from app.db.models.credencial_municipal import CredencialMunicipalTenant
from app.db.models.municipio import MunicipioNFSe, ProvedorNFSe
from app.db.models.tenant import Tenant
from app.nfse import credenciais as svc
from sqlalchemy import select


@pytest.fixture
def cofre() -> Cofre:
    # Cofre espera 32 bytes crus; base64 aqui estourava "tem 44".
    return Cofre(chave=b"k" * 32)


async def criar_tenant(sessao, slug: str) -> Tenant:
    tenant = Tenant(
        slug=slug,
        nome=f"Tenant {slug}",
        api_key_prefix=slug[:8],
        api_key_hash=f"hash-{slug}"[:16].ljust(16, "0"),
    )
    sessao.add(tenant)
    await sessao.flush()
    return tenant


async def criar_municipio(sessao, codigo: str = "5200258") -> MunicipioNFSe:
    """Idempotente: `municipios_nfse` não está na lista de truncate do conftest.

    Defeito de infraestrutura de teste registrado na auditoria — sem isto, o município
    criado num teste vaza para o seguinte e o INSERT estoura em unique violation.
    """
    existente = (
        await sessao.execute(select(MunicipioNFSe).where(MunicipioNFSe.codigo_ibge == codigo))
    ).scalar_one_or_none()
    if existente is not None:
        return existente
    municipio = MunicipioNFSe(
        codigo_ibge=codigo,
        nome="Aguas Lindas de Goias",
        uf="GO",
        provedor=ProvedorNFSe.NACIONAL_REST,
        fonte_url="https://www.gov.br/nfse",
    )
    sessao.add(municipio)
    await sessao.flush()
    return municipio


class TestSelo:
    async def test_segredo_vai_para_o_banco_cifrado(self, sessao_db, cofre) -> None:
        tenant = await criar_tenant(sessao_db, "c-selo-1")
        await criar_municipio(sessao_db)
        await svc.salvar(
            sessao_db,
            cofre=cofre,
            tenant_id=tenant.id,
            codigo_ibge="5200258",
            usuario_ws="usuario-secreto",
            senha_ws="senha-secreta",
        )
        await sessao_db.commit()

        bruto = (
            await sessao_db.execute(
                select(CredencialMunicipalTenant).where(
                    CredencialMunicipalTenant.tenant_id == tenant.id
                )
            )
        ).scalar_one()
        assert b"senha-secreta" not in bruto.senha_ws_criptografada
        assert bruto.senha_ws_criptografada != b"senha-secreta"

    async def test_abre_o_que_selou(self, sessao_db, cofre) -> None:
        tenant = await criar_tenant(sessao_db, "c-selo-2")
        await criar_municipio(sessao_db)
        cred = await svc.salvar(
            sessao_db,
            cofre=cofre,
            tenant_id=tenant.id,
            codigo_ibge="5200258",
            usuario_ws="user1",
            senha_ws="pass1",
            token_ws="tok1",
        )
        await sessao_db.commit()

        assert svc.segredo(cred, "usuario_ws", cofre=cofre) == "user1"
        assert svc.segredo(cred, "senha_ws", cofre=cofre) == "pass1"
        assert svc.segredo(cred, "token_ws", cofre=cofre) == "tok1"

    async def test_segredo_ausente_devolve_none(self, sessao_db, cofre) -> None:
        tenant = await criar_tenant(sessao_db, "c-selo-3")
        await criar_municipio(sessao_db)
        cred = await svc.salvar(sessao_db, cofre=cofre, tenant_id=tenant.id, codigo_ibge="5200258")
        await sessao_db.commit()
        assert svc.segredo(cred, "token_ws", cofre=cofre) is None

    async def test_rotacao_preserva_segredo_nao_informado(self, sessao_db, cofre) -> None:
        tenant = await criar_tenant(sessao_db, "c-selo-4")
        await criar_municipio(sessao_db)
        await svc.salvar(
            sessao_db,
            cofre=cofre,
            tenant_id=tenant.id,
            codigo_ibge="5200258",
            usuario_ws="user",
            token_ws="token-antigo",
        )
        cred = await svc.salvar(
            sessao_db,
            cofre=cofre,
            tenant_id=tenant.id,
            codigo_ibge="5200258",
            senha_ws="nova-senha",
        )
        await sessao_db.commit()
        assert svc.segredo(cred, "token_ws", cofre=cofre) == "token-antigo"
        assert svc.segredo(cred, "senha_ws", cofre=cofre) == "nova-senha"


class TestAAD:
    async def test_blob_de_outro_tenant_nao_abre(self, sessao_db, cofre) -> None:
        # AAD amarra tenant + IBGE: copiar o ciphertext para outro tenant falha no GCM.
        a = await criar_tenant(sessao_db, "c-aad-a")
        b = await criar_tenant(sessao_db, "c-aad-b")
        await criar_municipio(sessao_db)
        cred_a = await svc.salvar(
            sessao_db,
            cofre=cofre,
            tenant_id=a.id,
            codigo_ibge="5200258",
            senha_ws="segredo-de-a",
        )
        await sessao_db.commit()
        blob = cred_a.senha_ws_criptografada

        cred_b = CredencialMunicipalTenant(
            tenant_id=b.id, codigo_ibge="5200258", senha_ws_criptografada=blob
        )
        with pytest.raises(ErroDeCriptografia):
            svc.segredo(cred_b, "senha_ws", cofre=cofre)


class TestNumeracao:
    async def test_reserva_incrementa(self, sessao_db, cofre) -> None:
        tenant = await criar_tenant(sessao_db, "c-num-1")
        await criar_municipio(sessao_db)
        await svc.salvar(sessao_db, cofre=cofre, tenant_id=tenant.id, codigo_ibge="5200258")
        await sessao_db.commit()

        primeiro = await svc.reservar_numero_rps(
            sessao_db, tenant_id=tenant.id, codigo_ibge="5200258"
        )
        await sessao_db.commit()
        segundo = await svc.reservar_numero_rps(
            sessao_db, tenant_id=tenant.id, codigo_ibge="5200258"
        )
        await sessao_db.commit()
        assert primeiro == 1
        assert segundo == 2

    async def test_sem_credencial_levanta(self, sessao_db) -> None:
        tenant = await criar_tenant(sessao_db, "c-num-2")
        with pytest.raises(svc.ErroCredencial, match="sem credencial"):
            await svc.reservar_numero_rps(sessao_db, tenant_id=tenant.id, codigo_ibge="5200258")

    async def test_inativa_nao_reserva(self, sessao_db, cofre) -> None:
        tenant = await criar_tenant(sessao_db, "c-num-3")
        await criar_municipio(sessao_db)
        await svc.salvar(sessao_db, cofre=cofre, tenant_id=tenant.id, codigo_ibge="5200258")
        await sessao_db.commit()
        await svc.desativar(sessao_db, tenant_id=tenant.id, codigo_ibge="5200258")
        await sessao_db.commit()
        with pytest.raises(svc.ErroCredencial, match="inativa"):
            await svc.reservar_numero_rps(sessao_db, tenant_id=tenant.id, codigo_ibge="5200258")


class TestIsolamento:
    async def test_credencial_de_outro_tenant_nao_aparece(self, sessao_db, cofre) -> None:
        a = await criar_tenant(sessao_db, "c-iso-a")
        b = await criar_tenant(sessao_db, "c-iso-b")
        await criar_municipio(sessao_db)
        await svc.salvar(sessao_db, cofre=cofre, tenant_id=a.id, codigo_ibge="5200258")
        await sessao_db.commit()
        assert await svc.por_municipio(sessao_db, tenant_id=b.id, codigo_ibge="5200258") is None

    async def test_desativar_de_outro_tenant_devolve_false(self, sessao_db, cofre) -> None:
        a = await criar_tenant(sessao_db, "c-iso-c")
        b = await criar_tenant(sessao_db, "c-iso-d")
        await criar_municipio(sessao_db)
        await svc.salvar(sessao_db, cofre=cofre, tenant_id=a.id, codigo_ibge="5200258")
        await sessao_db.commit()
        assert await svc.desativar(sessao_db, tenant_id=b.id, codigo_ibge="5200258") is False
