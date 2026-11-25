"""Testes diretos de tenant (serviço + repositório) e do cofre de certificados.

Cobrem os caminhos que a API não exercita sozinha: rotação de chave, tenant
suspenso, slug duplicado, segredo de webhook selado na criação, e o ciclo de vida
do certificado (registrar → ativar → remover).

Estes são módulos de **segurança**: é onde uma falha vira acesso indevido, então a
cobertura aqui não é vaidade de métrica.
"""

from __future__ import annotations

import pytest
from app.certificates import service as certificados
from app.core.crypto import Cofre, aad_do_tenant
from app.db.models.enums import AmbienteFiscal, StatusTenant
from app.db.models.tenant import Tenant, TenantCertificate
from app.tenants import repository as repo
from app.tenants import service as tenants
from app.tenants.schemas import TenantCreate
from sqlalchemy import select

from tests.test_fase2_certificado import SENHA, gerar_pfx


class TestCriacao:
    async def test_cria_com_chave_e_prefixo(self, sessao_db) -> None:
        tenant, chave, segredo = await tenants.criar_tenant(
            sessao_db, TenantCreate(slug="alpha", nome="Alpha LTDA")
        )
        await sessao_db.commit()

        assert tenant.id is not None
        assert chave.startswith(tenant.api_key_prefix)
        assert segredo is None
        assert tenant.api_key_hash != chave, "o banco não guarda a chave em claro"

    async def test_slug_duplicado_levanta(self, sessao_db) -> None:
        await tenants.criar_tenant(sessao_db, TenantCreate(slug="beta", nome="Beta LTDA"))
        await sessao_db.commit()

        with pytest.raises(tenants.SlugJaExiste):
            await tenants.criar_tenant(sessao_db, TenantCreate(slug="beta", nome="Beta 2 LTDA"))

    async def test_com_webhook_gera_segredo_selado(self, sessao_db) -> None:
        tenant, _, segredo = await tenants.criar_tenant(
            sessao_db,
            TenantCreate(slug="gama", nome="Gama LTDA", webhook_url="https://gamma.test/hook"),
        )
        await sessao_db.commit()

        assert segredo is not None
        assert tenant.webhook_secret_selado is not None
        # O segredo precisa abrir com o aad do próprio tenant.
        aberto = Cofre(
            __import__("app.core.config", fromlist=["get_settings"]).get_settings().master_key()
        ).abrir(tenant.webhook_secret_selado, aad=aad_do_tenant(tenant.id))
        assert aberto.decode() == segredo

    async def test_segredo_nao_abre_em_outro_tenant(self, sessao_db, cliente) -> None:
        tenant, _, _ = await tenants.criar_tenant(
            sessao_db,
            TenantCreate(slug="delta", nome="Delta LTDA", webhook_url="https://d.test/h"),
        )
        await sessao_db.commit()
        outro, _, _ = await tenants.criar_tenant(
            sessao_db, TenantCreate(slug="epsilon", nome="Epsilon LTDA")
        )
        await sessao_db.commit()

        from app.core.config import get_settings

        cofre = Cofre(get_settings().master_key())
        with pytest.raises(Exception, match=r"contexto|aad|abrir"):
            cofre.abrir(tenant.webhook_secret_selado, aad=aad_do_tenant(outro.id))


class TestAutenticacao:
    async def test_chave_valida_autentica(self, sessao_db) -> None:
        tenant, chave, _ = await tenants.criar_tenant(
            sessao_db, TenantCreate(slug="zeta", nome="Zeta LTDA")
        )
        await sessao_db.commit()

        encontrado = await tenants.autenticar(sessao_db, chave)
        assert encontrado.id == tenant.id

    async def test_chave_curta_e_recusada(self, sessao_db) -> None:
        with pytest.raises(tenants.CredencialInvalida):
            await tenants.autenticar(sessao_db, "curta")

    async def test_chave_vazia_e_recusada(self, sessao_db) -> None:
        with pytest.raises(tenants.CredencialInvalida):
            await tenants.autenticar(sessao_db, "")

    async def test_chave_desconhecida(self, sessao_db) -> None:
        with pytest.raises(tenants.CredencialInvalida, match="inválida"):
            await tenants.autenticar(sessao_db, "x" * 40)

    async def test_tenant_suspenso(self, sessao_db) -> None:
        tenant, chave, _ = await tenants.criar_tenant(
            sessao_db, TenantCreate(slug="suspenso", nome="Suspenso LTDA")
        )
        tenant.status = StatusTenant.SUSPENSO
        await sessao_db.commit()

        with pytest.raises(tenants.TenantSuspenso, match="suspensa"):
            await tenants.autenticar(sessao_db, chave)


class TestRotacao:
    async def test_rotacionar_invalida_anterior(self, sessao_db) -> None:
        tenant, chave_antiga, _ = await tenants.criar_tenant(
            sessao_db, TenantCreate(slug="rotacao", nome="Rotação LTDA")
        )
        await sessao_db.commit()

        _, chave_nova = await tenants.rotacionar_chave(sessao_db, tenant.id)
        await sessao_db.commit()

        assert chave_nova != chave_antiga
        with pytest.raises(tenants.CredencialInvalida):
            await tenants.autenticar(sessao_db, chave_antiga)
        assert (await tenants.autenticar(sessao_db, chave_nova)).id == tenant.id

    async def test_rotacionar_tenant_inexistente(self, sessao_db) -> None:
        import uuid

        with pytest.raises(tenants.ErroDeTenant, match="não encontrado"):
            await tenants.rotacionar_chave(sessao_db, uuid.uuid4())


class TestObterEContar:
    async def test_obter_inexistente(self, sessao_db) -> None:
        import uuid

        with pytest.raises(tenants.ErroDeTenant, match="não encontrado"):
            await tenants.obter_tenant(sessao_db, uuid.uuid4())

    async def test_contar_e_listar(self, sessao_db) -> None:
        await tenants.criar_tenant(sessao_db, TenantCreate(slug="lista-1", nome="L1"))
        await tenants.criar_tenant(sessao_db, TenantCreate(slug="lista-2", nome="L2"))
        await sessao_db.commit()

        assert await repo.contar(sessao_db) >= 2
        listados = await repo.listar(sessao_db, limite=50, deslocamento=0)
        assert len(listados) >= 2

    async def test_por_slug_e_por_id(self, sessao_db) -> None:
        tenant, _, _ = await tenants.criar_tenant(
            sessao_db, TenantCreate(slug="busca", nome="Busca LTDA")
        )
        await sessao_db.commit()

        assert (await repo.por_slug(sessao_db, "busca")).id == tenant.id
        assert (await repo.por_id(sessao_db, tenant.id)).slug == "busca"
        assert await repo.por_slug(sessao_db, "nao-existe") is None

    async def test_repo_criar_direto(self, sessao_db) -> None:
        tenant = await repo.criar(
            sessao_db,
            slug="direto",
            nome="Direto LTDA",
            api_key_prefix="abc12345",
            api_key_hash="h" * 64,
        )
        await sessao_db.commit()
        assert tenant.slug == "direto"

    async def test_atualizar_hash_de_chave(self, sessao_db) -> None:
        tenant, _, _ = await tenants.criar_tenant(
            sessao_db, TenantCreate(slug="hash", nome="Hash LTDA")
        )
        await sessao_db.commit()

        await repo.atualizar_hash_de_chave(
            sessao_db, tenant, prefixo="prefixo2", chave_hash="y" * 64
        )
        await sessao_db.commit()
        await sessao_db.refresh(tenant)
        assert tenant.api_key_hash == "y" * 64


class TestConfiguracaoFiscal:
    async def test_upsert_cria_e_atualiza(self, sessao_db) -> None:
        tenant, _, _ = await tenants.criar_tenant(
            sessao_db, TenantCreate(slug="cfg", nome="Cfg LTDA")
        )
        await sessao_db.commit()

        primeira = await tenants.definir_config_fiscal(
            sessao_db,
            tenant.id,
            {
                "municipio_ibge": "3550308",
                "uf": "SP",
                "ambiente": AmbienteFiscal.HOMOLOGACAO,
                "codigo_tributacao_nacional": "010701",
                "serie_dps": "1",
            },
        )
        await sessao_db.commit()
        assert primeira.id is not None

        segunda = await tenants.definir_config_fiscal(
            sessao_db,
            tenant.id,
            {
                "municipio_ibge": "3550308",
                "uf": "SP",
                "ambiente": AmbienteFiscal.HOMOLOGACAO,
                "codigo_tributacao_nacional": "010701",
                "serie_dps": "2",
            },
        )
        await sessao_db.commit()
        assert segunda.id == primeira.id, "upsert não pode criar segunda configuração"
        assert segunda.serie_dps == "2"

    async def test_listar_configs_e_config_do_municipio(self, sessao_db) -> None:
        tenant, _, _ = await tenants.criar_tenant(
            sessao_db, TenantCreate(slug="cfg2", nome="Cfg2 LTDA")
        )
        await sessao_db.commit()
        await tenants.definir_config_fiscal(
            sessao_db,
            tenant.id,
            {
                "municipio_ibge": "3304557",
                "uf": "RJ",
                "ambiente": AmbienteFiscal.HOMOLOGACAO,
                "codigo_tributacao_nacional": "010701",
                "serie_dps": "1",
            },
        )
        await sessao_db.commit()

        configs = await repo.listar_configs(sessao_db, tenant.id)
        assert configs
        achada = await repo.config_do_municipio(
            sessao_db, tenant.id, "3304557", AmbienteFiscal.HOMOLOGACAO
        )
        assert achada is not None


class TestCertificados:
    async def _tenant(self, sessao_db) -> Tenant:
        tenant, _, _ = await tenants.criar_tenant(
            sessao_db, TenantCreate(slug="cert-tenant", nome="Cert LTDA")
        )
        await sessao_db.commit()
        return tenant

    async def test_registrar_e_listar(self, sessao_db) -> None:
        tenant = await self._tenant(sessao_db)
        registro = await certificados.registrar(
            sessao_db,
            tenant.id,
            apelido="principal",
            pfx=gerar_pfx(),
            senha=SENHA.decode(),
        )
        await sessao_db.commit()

        assert registro.valido_ate is not None, "validade precisa ser extraída do PFX"
        assert registro.ativo is True
        listados = await certificados.listar(sessao_db, tenant.id)
        assert len(listados) == 1

    async def test_duplicado_levanta(self, sessao_db) -> None:
        tenant = await self._tenant(sessao_db)
        pfx = gerar_pfx()
        await certificados.registrar(
            sessao_db, tenant.id, apelido="a", pfx=pfx, senha=SENHA.decode()
        )
        await sessao_db.commit()

        with pytest.raises(certificados.CertificadoDuplicado):
            await certificados.registrar(
                sessao_db, tenant.id, apelido="b", pfx=pfx, senha=SENHA.decode()
            )

    async def test_ativo_e_por_fingerprint(self, sessao_db) -> None:
        tenant = await self._tenant(sessao_db)
        registro = await certificados.registrar(
            sessao_db, tenant.id, apelido="a", pfx=gerar_pfx(), senha=SENHA.decode()
        )
        await sessao_db.commit()

        assert (await certificados.ativo(sessao_db, tenant.id)).id == registro.id
        achado = await certificados.por_fingerprint(
            sessao_db, tenant.id, registro.fingerprint_sha256
        )
        assert achado is not None
        assert await certificados.por_fingerprint(sessao_db, tenant.id, "nao-existe") is None

    async def test_ativo_inexistente_devolve_none(self, sessao_db) -> None:
        tenant = await self._tenant(sessao_db)
        assert await certificados.ativo(sessao_db, tenant.id) is None

    async def test_por_id_inexistente_levanta(self, sessao_db) -> None:
        import uuid

        tenant = await self._tenant(sessao_db)
        with pytest.raises(certificados.CertificadoNaoEncontrado):
            await certificados.por_id(sessao_db, tenant.id, uuid.uuid4())

    async def test_ativar_troca_o_ativo(self, sessao_db) -> None:
        tenant = await self._tenant(sessao_db)
        primeiro = await certificados.registrar(
            sessao_db, tenant.id, apelido="a", pfx=gerar_pfx(), senha=SENHA.decode()
        )
        await sessao_db.commit()
        segundo = await certificados.registrar(
            sessao_db, tenant.id, apelido="b", pfx=gerar_pfx(), senha=SENHA.decode()
        )
        await sessao_db.commit()

        ativado = await certificados.ativar(sessao_db, tenant.id, primeiro.id)
        await sessao_db.commit()

        assert ativado.id == primeiro.id
        todos = (await sessao_db.execute(select(TenantCertificate))).scalars().all()
        ativos = [c for c in todos if c.ativo]
        assert len(ativos) == 1, "só um certificado pode estar ativo por tenant"
        assert ativos[0].id == primeiro.id
        assert segundo.id != ativos[0].id

    async def test_remover(self, sessao_db) -> None:
        tenant = await self._tenant(sessao_db)
        registro = await certificados.registrar(
            sessao_db, tenant.id, apelido="a", pfx=gerar_pfx(), senha=SENHA.decode()
        )
        await sessao_db.commit()

        await certificados.remover(sessao_db, tenant.id, registro.id)
        await sessao_db.commit()
        assert await certificados.ativo(sessao_db, tenant.id) is None

    async def test_remover_todos(self, sessao_db) -> None:
        tenant = await self._tenant(sessao_db)
        await certificados.registrar(
            sessao_db, tenant.id, apelido="a", pfx=gerar_pfx(), senha=SENHA.decode()
        )
        await sessao_db.commit()
        removidos = await certificados.remover_todos(sessao_db, tenant.id)
        await sessao_db.commit()
        assert removidos == 1

    async def test_abrir_em_memoria(self, sessao_db) -> None:
        tenant = await self._tenant(sessao_db)
        registro = await certificados.registrar(
            sessao_db, tenant.id, apelido="a", pfx=gerar_pfx(), senha=SENHA.decode()
        )
        await sessao_db.commit()

        certificado = certificados.abrir_em_memoria(registro)
        assert certificado.cnpj == "11222333000181"
        # Contexto TLS pronto para mTLS.
        contexto = certificado.ssl_context()
        assert contexto is not None
