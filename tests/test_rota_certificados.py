"""Rotas de certificado A1 — testadas na função, com dublês (sem banco, sem PFX real).

O que importa aqui não é o caminho feliz, é o **contrato de recusa**: arquivo vazio (422), arquivo
grande demais (413), certificado repetido (409), PFX ilegível (422) — e, em todos, o rollback. Também
o aviso de validade: expirado, expirando e saudável têm mensagens diferentes porque a ação do cliente
é diferente.

Nenhum PFX real é usado: o cofre é substituído. O certificado verdadeiro foi exercitado fora da suíte,
em prova local de assinatura (docs/auditoria_inicial.md §90).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.api.v1 import certificados as rota
from app.certificates.cofre import ErroCertificado
from app.certificates.service import CertificadoDuplicado, CertificadoNaoEncontrado
from fastapi import HTTPException


class DbFalsa:
    def __init__(self, linhas: list | None = None) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.refreshes = 0
        self._linhas = linhas or []

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, objeto: object) -> None:
        self.refreshes += 1

    async def execute(self, consulta: object) -> ResultadoFalso:
        return ResultadoFalso(self._linhas)


class ResultadoFalso:
    def __init__(self, linhas: list) -> None:
        self._linhas = linhas

    def scalars(self) -> ResultadoFalso:
        return self

    def all(self) -> list:
        return self._linhas


class UploadFalso:
    def __init__(self, conteudo: bytes) -> None:
        self._conteudo = conteudo

    async def read(self) -> bytes:
        return self._conteudo


TENANT = SimpleNamespace(id=uuid.uuid4())


def _registro(dias: int = 200, ativo: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        apelido="matriz",
        cnpj="64339333000122",
        subject_cn="LEANDRO MARCOS PRADO",
        emissor="ICP-Brasil",
        numero_serie="1A2B",
        valido_de=datetime.now(UTC) - timedelta(days=365),
        valido_ate=datetime.now(UTC) + timedelta(days=dias),
        fingerprint_sha256="f" * 64,
        ativo=ativo,
        created_at=datetime.now(UTC),
    )


class TestSaida:
    def test_calcula_dias_restantes(self) -> None:
        saida = rota._saida(_registro(dias=41))

        assert saida.dias_restantes in (40, 41)

    def test_validade_ingenua_recebe_utc(self) -> None:
        registro = _registro()
        registro.valido_ate = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=10)

        assert rota._saida(registro).dias_restantes in (9, 10)

    def test_sem_validade_nao_calcula(self) -> None:
        registro = _registro()
        registro.valido_ate = None

        assert rota._saida(registro).dias_restantes is None


class TestUpload:
    async def test_arquivo_vazio_vira_422(self, monkeypatch) -> None:
        db = DbFalsa()

        with pytest.raises(HTTPException) as erro:
            await rota.enviar_certificado(UploadFalso(b""), "x", "apelido", TENANT, db)

        assert erro.value.status_code == 422
        assert erro.value.detail == "arquivo vazio"

    async def test_arquivo_grande_vira_413(self) -> None:
        db = DbFalsa()
        grande = b"x" * (rota.TAMANHO_MAXIMO_PFX + 1)

        with pytest.raises(HTTPException) as erro:
            await rota.enviar_certificado(UploadFalso(grande), "x", "apelido", TENANT, db)

        assert erro.value.status_code == 413

    async def test_duplicado_vira_409_e_faz_rollback(self, monkeypatch) -> None:
        async def registrar(*a, **k):
            raise CertificadoDuplicado("já existe")

        monkeypatch.setattr(rota.service, "registrar", registrar)
        db = DbFalsa()

        with pytest.raises(HTTPException) as erro:
            await rota.enviar_certificado(UploadFalso(b"pfx"), "x", "apelido", TENANT, db)

        assert erro.value.status_code == 409
        assert db.rollbacks == 1

    async def test_pfx_ilegivel_vira_422_e_faz_rollback(self, monkeypatch) -> None:
        async def registrar(*a, **k):
            raise ErroCertificado("senha incorreta")

        monkeypatch.setattr(rota.service, "registrar", registrar)
        db = DbFalsa()

        with pytest.raises(HTTPException) as erro:
            await rota.enviar_certificado(UploadFalso(b"pfx"), "errada", "apelido", TENANT, db)

        assert erro.value.status_code == 422
        assert db.rollbacks == 1

    async def test_sucesso_commita_e_devolve_metadados(self, monkeypatch) -> None:
        registro = _registro()
        chamadas: list = []

        async def registrar(db, tenant_id, **kwargs):
            chamadas.append(kwargs)
            return registro

        monkeypatch.setattr(rota.service, "registrar", registrar)
        db = DbFalsa()

        saida = await rota.enviar_certificado(UploadFalso(b"pfx"), "senha", "matriz", TENANT, db)

        assert saida.apelido == "matriz"
        assert db.commits == 1 and db.refreshes == 1
        assert chamadas[0]["apelido"] == "matriz"


class TestListagem:
    async def test_lista_do_tenant(self, monkeypatch) -> None:
        async def listar(db, tenant_id):
            return [_registro(), _registro(ativo=False)]

        monkeypatch.setattr(rota.service, "listar", listar)

        saida = await rota.listar_certificados(TENANT, DbFalsa())

        assert [c.apelido for c in saida] == ["matriz", "matriz"]


class TestSaude:
    async def test_sem_certificado_avisa(self, monkeypatch) -> None:
        async def ativo(db, tenant_id):
            return None

        monkeypatch.setattr(rota.service, "ativo", ativo)

        saida = await rota.saude_certificado(TENANT, DbFalsa())

        assert saida.existe is False
        assert "emissão não funciona" in saida.aviso

    async def test_expirado_avisa_tls(self, monkeypatch) -> None:
        async def ativo(db, tenant_id):
            return _registro(dias=-5)

        monkeypatch.setattr(rota.service, "ativo", ativo)

        saida = await rota.saude_certificado(TENANT, DbFalsa())

        assert saida.expirado is True
        assert "expirado" in saida.aviso

    async def test_expirando_avisa_dias(self, monkeypatch) -> None:
        async def ativo(db, tenant_id):
            return _registro(dias=12)

        monkeypatch.setattr(rota.service, "ativo", ativo)

        saida = await rota.saude_certificado(TENANT, DbFalsa())

        assert saida.expirado is False
        assert "expira em" in saida.aviso

    async def test_saudavel_sem_aviso(self, monkeypatch) -> None:
        async def ativo(db, tenant_id):
            return _registro(dias=200)

        monkeypatch.setattr(rota.service, "ativo", ativo)

        saida = await rota.saude_certificado(TENANT, DbFalsa())

        assert saida.aviso is None and saida.existe is True


class TestAtivarRemover:
    async def test_ativar_commita(self, monkeypatch) -> None:
        registro = _registro(ativo=True)

        async def ativar(db, tenant_id, certificado_id):
            return registro

        monkeypatch.setattr(rota.service, "ativar", ativar)
        db = DbFalsa()

        saida = await rota.ativar_certificado(registro.id, TENANT, db)

        assert saida.id == registro.id and db.commits == 1

    async def test_ativar_inexistente_vira_404(self, monkeypatch) -> None:
        async def ativar(db, tenant_id, certificado_id):
            raise CertificadoNaoEncontrado("não é deste tenant")

        monkeypatch.setattr(rota.service, "ativar", ativar)
        db = DbFalsa()

        with pytest.raises(HTTPException) as erro:
            await rota.ativar_certificado(uuid.uuid4(), TENANT, db)

        assert erro.value.status_code == 404
        assert db.rollbacks == 1

    async def test_remover_commita(self, monkeypatch) -> None:
        async def remover(db, tenant_id, certificado_id):
            return None

        monkeypatch.setattr(rota.service, "remover", remover)
        db = DbFalsa()

        assert await rota.remover_certificado(uuid.uuid4(), TENANT, db) is None
        assert db.commits == 1

    async def test_remover_inexistente_vira_404(self, monkeypatch) -> None:
        async def remover(db, tenant_id, certificado_id):
            raise CertificadoNaoEncontrado("sumiu")

        monkeypatch.setattr(rota.service, "remover", remover)
        db = DbFalsa()

        with pytest.raises(HTTPException) as erro:
            await rota.remover_certificado(uuid.uuid4(), TENANT, db)

        assert erro.value.status_code == 404 and db.rollbacks == 1


class TestUsos:
    async def test_certificado_de_outro_tenant_vira_404(self, monkeypatch) -> None:
        async def por_id(db, tenant_id, certificado_id):
            raise CertificadoNaoEncontrado("não é deste tenant")

        monkeypatch.setattr(rota.service, "por_id", por_id)

        with pytest.raises(HTTPException) as erro:
            await rota.usos_do_certificado(uuid.uuid4(), TENANT, DbFalsa(), limite=50)

        assert erro.value.status_code == 404

    async def test_historico_serializa_sem_mensagem_de_erro(self, monkeypatch) -> None:
        async def por_id(db, tenant_id, certificado_id):
            return _registro()

        monkeypatch.setattr(rota.service, "por_id", por_id)
        linha = SimpleNamespace(
            id=uuid.uuid4(),
            operacao="emissao",
            ambiente="homologacao",
            sucesso=False,
            erro_tipo="ErroTransporte",
            em=datetime(2026, 11, 28, tzinfo=UTC),
            created_at=datetime(2026, 11, 28, tzinfo=UTC),
        )

        saida = await rota.usos_do_certificado(
            uuid.uuid4(), TENANT, DbFalsa(linhas=[linha]), limite=50
        )

        assert len(saida) == 1
        assert saida[0].erro_tipo == "ErroTransporte"
        assert not hasattr(saida[0], "mensagem")
