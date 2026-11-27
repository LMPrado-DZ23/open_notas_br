"""Rotação da chave-mestra: reabre e re-sela todo material cifrado.

**Por que existe.** Até aqui, trocar `MASTER_ENCRYPTION_KEY` tornava ilegível tudo que estava
selado — certificado A1, segredo de webhook, credenciais municipais, tokens do Melhor Envio. O
runbook (`docs/OPERACAO.md` §5.2) só podia dizer "reenvie tudo à mão". Este módulo faz a
re-selagem com uma chave nova, sem tocar nos dados em claro.

**Como funciona.** Para cada linha: abre o envelope com a chave **antiga**, usando o MESMO `aad`
com que foi selado (o `aad` amarra o blob a tenant e, em credencial municipal, também ao
município), e sela de novo com a chave **nova**. O `aad` não muda — só a chave.

**Garantias que o código impõe:**

- roda em **uma transação**: metade migrado é pior que nada migrado;
- **verifica depois**: reabre cada envelope gravado com a chave nova antes do commit; se qualquer
  um falhar, nada é aplicado;
- **recusa** chave nova ausente, igual à antiga ou malformada;
- não imprime conteúdo nem chave — só contagens.

Uso (chaves por variável de ambiente; nunca por argumento de linha de comando):

    MASTER_ENCRYPTION_KEY=<antiga> \
    MASTER_ENCRYPTION_KEY_NOVA=<nova> \
    python -m scripts.rotacionar_chave_mestra

Depois de rodar: atualize a variável de ambiente do serviço para a chave nova e reinicie.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass

from app.core.crypto import Cofre, ErroDeCriptografia, aad_do_tenant
from app.db.models.credencial_municipal import CredencialMunicipalTenant
from app.db.models.frete import FreteCredencial
from app.db.models.tenant import Tenant, TenantCertificate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

#: Nome do campo, para o relatório. Nada aqui é segredo.
_ALVO = "re-selagem da chave-mestra"


@dataclass(frozen=True, slots=True)
class Resultado:
    por_tabela: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.por_tabela.values())


def decodificar_chave(valor: str, *, nome: str) -> bytes:
    """Decodifica base64 de exatamente 32 bytes, com mensagem de erro útil."""
    bruto = (valor or "").strip()
    if not bruto:
        raise ValueError(f"{nome} ausente")
    try:
        chave = base64.b64decode(bruto, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{nome} não é base64 válido") from exc
    if len(chave) != 32:
        raise ValueError(f"{nome} precisa ter 32 bytes (tem {len(chave)})")
    return chave


def _aad_credencial_municipal(tenant_id: object, codigo_ibge: str) -> bytes:
    """Mesmo `aad` de `app/nfse/credenciais.py`: tenant + município."""
    return aad_do_tenant(tenant_id) + b"|" + codigo_ibge.encode("utf-8")


async def _reselar(
    registros: Iterable[tuple[object, list[str], bytes]],
    *,
    antigo: Cofre,
    novo: Cofre,
) -> int:
    """Re-sela os campos indicados de cada registro. Devolve quantos campos mudaram."""
    alterados = 0
    for registro, campos, aad in registros:
        for campo in campos:
            envelope = getattr(registro, campo)
            if envelope is None:
                continue
            claro = antigo.abrir(envelope, aad=aad)
            setattr(registro, campo, novo.selar(claro, aad=aad))
            alterados += 1
    return alterados


async def rotacionar(sessao: AsyncSession, *, antiga: bytes, nova: bytes) -> Resultado:
    """Re-sela todo material cifrado da chave `antiga` para `nova`.

    Não faz commit: quem chama decide. Erro de decifragem em **qualquer** linha aborta a
    operação inteira — significa que a chave antiga informada não é a que selou aquele dado.
    """
    if antiga == nova:
        raise ValueError("a chave nova é igual à antiga; nada a fazer")
    antigo, novo = Cofre(antiga), Cofre(nova)
    resultado: dict[str, int] = {}

    # Certificados A1: `selar_pfx` guarda PFX e senha no MESMO envelope.
    certificados = (await sessao.execute(select(TenantCertificate))).scalars().all()
    resultado["tenant_certificates"] = await _reselar(
        ((c, ["pfx_selado", "senha_selada"], aad_do_tenant(c.tenant_id)) for c in certificados),
        antigo=antigo,
        novo=novo,
    )

    tenants = (await sessao.execute(select(Tenant))).scalars().all()
    resultado["tenants"] = await _reselar(
        ((t, ["webhook_secret_selado"], aad_do_tenant(t.id)) for t in tenants),
        antigo=antigo,
        novo=novo,
    )

    credenciais = (await sessao.execute(select(CredencialMunicipalTenant))).scalars().all()
    resultado["credenciais_municipais"] = await _reselar(
        (
            (
                c,
                ["usuario_ws_criptografado", "senha_ws_criptografada", "token_ws_criptografado"],
                _aad_credencial_municipal(c.tenant_id, c.codigo_ibge),
            )
            for c in credenciais
        ),
        antigo=antigo,
        novo=novo,
    )

    frete = (await sessao.execute(select(FreteCredencial))).scalars().all()
    resultado["frete_credenciais"] = await _reselar(
        (
            (f, ["access_token_selado", "refresh_token_selado"], aad_do_tenant(f.tenant_id))
            for f in frete
        ),
        antigo=antigo,
        novo=novo,
    )

    return Resultado(por_tabela=resultado)


async def verificar(sessao: AsyncSession, *, nova: bytes) -> int:
    """Reabre com a chave nova todo envelope que deveria estar migrado.

    Devolve quantos abriram. Levanta `ErroDeCriptografia` no primeiro que falhar — é a prova de
    que a rotação realmente cobriu o material.
    """
    cofre = Cofre(nova)
    abertos = 0

    for c in (await sessao.execute(select(TenantCertificate))).scalars().all():
        cofre.abrir(c.pfx_selado, aad=aad_do_tenant(c.tenant_id))
        abertos += 1
        if c.senha_selada is not None:
            cofre.abrir(c.senha_selada, aad=aad_do_tenant(c.tenant_id))
            abertos += 1

    for t in (await sessao.execute(select(Tenant))).scalars().all():
        if t.webhook_secret_selado is not None:
            cofre.abrir(t.webhook_secret_selado, aad=aad_do_tenant(t.id))
            abertos += 1

    for cm in (await sessao.execute(select(CredencialMunicipalTenant))).scalars().all():
        aad = _aad_credencial_municipal(cm.tenant_id, cm.codigo_ibge)
        for campo in (
            "usuario_ws_criptografado",
            "senha_ws_criptografada",
            "token_ws_criptografado",
        ):
            envelope = getattr(cm, campo)
            if envelope is not None:
                cofre.abrir(envelope, aad=aad)
                abertos += 1

    for f in (await sessao.execute(select(FreteCredencial))).scalars().all():
        cofre.abrir(f.access_token_selado, aad=aad_do_tenant(f.tenant_id))
        abertos += 1
        if f.refresh_token_selado is not None:
            cofre.abrir(f.refresh_token_selado, aad=aad_do_tenant(f.tenant_id))
            abertos += 1

    return abertos


async def executar() -> int:
    """Fluxo de linha de comando: lê as duas chaves do ambiente e aplica em uma transação."""
    from app.db.session import obter_sessionmaker

    try:
        antiga = decodificar_chave(
            os.environ.get("MASTER_ENCRYPTION_KEY", ""), nome="MASTER_ENCRYPTION_KEY"
        )
        nova = decodificar_chave(
            os.environ.get("MASTER_ENCRYPTION_KEY_NOVA", ""), nome="MASTER_ENCRYPTION_KEY_NOVA"
        )
    except ValueError as exc:
        print(f"recusando rodar: {exc}", file=sys.stderr)
        return 2

    print(f"[..] {_ALVO}")
    async with obter_sessionmaker()() as sessao:
        try:
            resultado = await rotacionar(sessao, antiga=antiga, nova=nova)
        except ErroDeCriptografia as exc:
            await sessao.rollback()
            print(
                f"falhou: um envelope não abriu com a chave antiga ({exc}). "
                "Nada foi gravado — a chave informada não é a que selou este dado.",
                file=sys.stderr,
            )
            return 1
        except ValueError as exc:
            await sessao.rollback()
            print(f"falhou: {exc}", file=sys.stderr)
            return 1

        try:
            abertos = await verificar(sessao, nova=nova)
        except ErroDeCriptografia as exc:
            await sessao.rollback()
            print(f"falhou na verificação: {exc}. Nada foi gravado.", file=sys.stderr)
            return 1

        await sessao.commit()

    for tabela, quantidade in resultado.por_tabela.items():
        print(f"  {tabela}: {quantidade} campo(s) re-selado(s)")
    print(f"[OK] {resultado.total} campo(s) re-selado(s); {abertos} reaberto(s) com a chave nova")
    print("Agora atualize MASTER_ENCRYPTION_KEY do serviço para a chave nova e reinicie.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(executar()))
