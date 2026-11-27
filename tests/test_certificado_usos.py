"""Auditoria de uso do certificado (§71).

O cofre guardava o certificado, mas não o uso. Sem registro, "este A1 foi usado para quê?" não tem
resposta — pergunta obrigatória para operar credencial fiscal de terceiros.

O que precisa ser provado:

1. uso bem-sucedido **é registrado**, com a operação certa;
2. falha de abertura também é registrada (com o **tipo** do erro, nunca a mensagem);
3. o registro **não** contém segredo nem XML;
4. a consulta é isolada por tenant — outro tenant recebe 404, não a lista.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select

from tests.test_fase2_certificado import SENHA, gerar_pfx

UUID = uuid.UUID

OPERACAO_STATUS = "status_transporte"


def cabecalho(tenant: dict[str, Any]) -> dict[str, str]:
    return {"X-API-Key": tenant["api_key"]}


async def _tenant_com_certificado(cliente, slug: str, ibge: str, uf: str) -> dict[str, Any]:
    criado = await cliente.post("/v1/tenants", json={"slug": slug, "nome": f"{slug} LTDA"})
    assert criado.status_code == 201, criado.text
    tenant = criado.json()

    await cliente.put(
        "/v1/me/config-fiscal",
        json={
            "municipio_ibge": ibge,
            "uf": uf,
            "ambiente": "homologacao",
            "codigo_tributacao_nacional": "010701",
            "serie_dps": "1",
            "aliquota_iss": 0.05,
        },
        headers=cabecalho(tenant),
    )
    certificado = await cliente.post(
        "/v1/me/certificados",
        files={"arquivo": ("c.pfx", gerar_pfx(), "application/x-pkcs12")},
        data={"senha": SENHA.decode(), "apelido": "a1"},
        headers=cabecalho(tenant),
    )
    assert certificado.status_code == 201, certificado.text
    tenant["certificado_id"] = certificado.json()["id"]
    return tenant


class TestRegistro:
    async def test_emissao_registra_uso(self, cliente, sessao_db) -> None:
        from app.db.models.certificado_uso import CertificadoUso

        tenant = await _tenant_com_certificado(cliente, "uso-a", "5200258", "GO")

        emitida = await cliente.post(
            "/v1/emissoes",
            json={"idempotency_key": "uso-0001", "valor": "10.00", "descricao": "Servico"},
            headers=cabecalho(tenant),
        )
        assert emitida.status_code == 201, emitida.text

        linhas = (
            (
                await sessao_db.execute(
                    select(CertificadoUso).where(CertificadoUso.operacao == "emissao")
                )
            )
            .scalars()
            .all()
        )
        assert linhas, "emissao deveria registrar uso do certificado"
        assert linhas[0].sucesso is True
        assert linhas[0].ambiente is None or isinstance(linhas[0].ambiente, str)

    async def test_falha_de_abertura_e_registrada(self, sessao_db) -> None:
        """Chave-mestra trocada só aparece no uso: a falha precisa virar linha de auditoria."""
        from app.certificates import service as cert_service
        from app.certificates.cofre import ErroCertificado
        from app.core.crypto import ErroDeCriptografia
        from app.db.models.certificado_uso import CertificadoUso
        from app.db.models.tenant import Tenant, TenantCertificate

        tenant = Tenant(
            slug="uso-falha",
            nome="Uso Falha LTDA",
            api_key_prefix="usofalha",
            api_key_hash="hash-uso-falha".ljust(16, "0")[:16],
        )
        sessao_db.add(tenant)
        await sessao_db.flush()

        registro = TenantCertificate(
            tenant_id=tenant.id,
            apelido="a1",
            cnpj="11222333000181",
            fingerprint_sha256="f" * 64,
            pfx_selado=b"envelope-invalido",
            ativo=True,
        )
        sessao_db.add(registro)
        await sessao_db.commit()

        with pytest.raises((ErroCertificado, ErroDeCriptografia)):
            await cert_service.abrir_para_uso(sessao_db, registro, operacao="emissao")
        await sessao_db.commit()

        linha = (
            await sessao_db.execute(
                select(CertificadoUso).where(CertificadoUso.certificado_id == registro.id)
            )
        ).scalar_one()
        assert linha.sucesso is False
        assert linha.erro_tipo, "tipo do erro precisa ficar registrado"
        # Mensagem de exceção pode carregar dado do cliente: só o tipo é guardado.
        assert "envelope-invalido" not in (linha.erro_tipo or "")


class TestSemSegredo:
    async def test_registro_nao_guarda_segredo(self, cliente, sessao_db) -> None:
        from app.db.models.certificado_uso import CertificadoUso

        tenant = await _tenant_com_certificado(cliente, "uso-b", "3550308", "SP")
        await cliente.post(
            "/v1/emissoes",
            json={"idempotency_key": "uso-0002", "valor": "10.00", "descricao": "Servico"},
            headers=cabecalho(tenant),
        )

        linha = (
            await sessao_db.execute(
                select(CertificadoUso).where(
                    CertificadoUso.certificado_id == UUID(tenant["certificado_id"])
                )
            )
        ).scalar_one()

        texto = repr(linha.__dict__).lower()
        for proibido in ("pfx", "senha", "signature", "xml", "chave privada"):
            assert proibido not in texto, f"campo proibido no registro: {proibido}"


class TestConsulta:
    async def test_historico_lista_os_usos(self, cliente) -> None:
        tenant = await _tenant_com_certificado(cliente, "uso-c", "3509502", "SP")
        await cliente.post(
            "/v1/emissoes",
            json={"idempotency_key": "uso-0003", "valor": "10.00", "descricao": "Servico"},
            headers=cabecalho(tenant),
        )

        resposta = await cliente.get(
            f"/v1/me/certificados/{tenant['certificado_id']}/usos", headers=cabecalho(tenant)
        )

        assert resposta.status_code == 200, resposta.text
        usos = resposta.json()
        assert usos
        assert usos[0]["operacao"] in {"emissao", "cancelamento", "evento"}

    async def test_outro_tenant_nao_ve_historico(self, cliente) -> None:
        dono = await _tenant_com_certificado(cliente, "uso-d", "3304557", "RJ")
        intruso = await _tenant_com_certificado(cliente, "uso-e", "3106200", "MG")

        resposta = await cliente.get(
            f"/v1/me/certificados/{dono['certificado_id']}/usos", headers=cabecalho(intruso)
        )

        assert resposta.status_code == 404, "histórico de uso não pode vazar entre tenants"


class TestSobrescrita:
    """A remoção sobrescreve o envelope antes de apagar a linha (§74).

    Excluir só a linha deixa o ciphertext em páginas antigas e no WAL. Não é possível provar
    irrecuperabilidade de um dump — isso não existe em software —, então o teste prova o que é
    verificável: os bytes mudam, o tamanho é preservado e nada de segredo aparece no objeto.
    """

    def _registro(self, pfx: bytes, senha: bytes | None):
        from app.db.models.tenant import TenantCertificate

        return TenantCertificate(
            tenant_id=uuid.uuid4(),
            apelido="a1",
            cnpj="11222333000181",
            fingerprint_sha256="f" * 64,
            pfx_selado=pfx,
            senha_selada=senha,
        )

    def test_bytes_mudam_e_tamanho_e_preservado(self) -> None:
        from app.certificates import service as cert_service

        pfx = b"conteudo-do-pfx-falso" * 3
        senha = b"senha-falsa"
        registro = self._registro(pfx, senha)

        cert_service._sobrescrever_envelope(registro)

        assert registro.pfx_selado != pfx
        assert len(registro.pfx_selado) == len(pfx)
        assert registro.senha_selada != senha
        assert len(registro.senha_selada) == len(senha)

    def test_sem_senha_nao_quebra(self) -> None:
        from app.certificates import service as cert_service

        registro = self._registro(b"pfx", None)

        cert_service._sobrescrever_envelope(registro)

        assert registro.senha_selada is None

    async def test_remocao_apaga_a_linha(self, cliente, sessao_db) -> None:
        """Contraprova: sobrescrever não pode impedir a exclusão de fato."""
        from app.db.models.tenant import TenantCertificate
        from sqlalchemy import select

        criado = await cliente.post("/v1/tenants", json={"slug": "del-1", "nome": "Del LTDA"})
        tenant = criado.json()
        await cliente.put(
            "/v1/me/config-fiscal",
            json={
                "municipio_ibge": "3550308",
                "uf": "SP",
                "ambiente": "homologacao",
                "codigo_tributacao_nacional": "010701",
                "serie_dps": "1",
                "aliquota_iss": 0.05,
            },
            headers={"X-API-Key": tenant["api_key"]},
        )
        certificado = await cliente.post(
            "/v1/me/certificados",
            files={"arquivo": ("c.pfx", gerar_pfx(), "application/x-pkcs12")},
            data={"senha": SENHA.decode(), "apelido": "a1"},
            headers={"X-API-Key": tenant["api_key"]},
        )
        assert certificado.status_code == 201, certificado.text
        cert_id = certificado.json()["id"]

        resposta = await cliente.delete(
            f"/v1/me/certificados/{cert_id}", headers={"X-API-Key": tenant["api_key"]}
        )
        assert resposta.status_code == 204, resposta.text

        restante = (
            await sessao_db.execute(
                select(TenantCertificate).where(TenantCertificate.id == uuid.UUID(cert_id))
            )
        ).scalar_one_or_none()
        assert restante is None
