"""Gera docs/PAINEL.md medindo o estado real.

Regra que este script existe para garantir: **se a medição falhar, abortar**. O bug
anterior gravou `Testes coletados: 0` num projeto com 1068 testes porque o regex não
casou e o script seguiu em frente. Um painel que se diz derivado não pode inventar zero
em silêncio.

Uso:
    python -m scripts.gerar_painel            # mede e grava
    python -m scripts.gerar_painel --check    # mede e compara, sem gravar
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PAINEL = RAIZ / "docs" / "PAINEL.md"


class ErroDeMedicao(Exception):
    """A medição não produziu número. Abortar é obrigatório: nunca gravar default."""


def medir_testes() -> int:
    """Conta testes pelo relatório JUnit, não por regex de texto.

    A primeira versão procurava "N passed" na saída do pytest e **não achava** — o que
    fez o gerador abortar (comportamento certo) em vez de gravar 0. O JUnit é
    determinístico: um `<testcase>` por teste, sem depender de formatação de resumo.
    """
    import tempfile
    import xml.etree.ElementTree as ET

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as arquivo:
        destino = pathlib.Path(arquivo.name)
    try:
        saida = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", f"--junit-xml={destino}"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if not destino.is_file() or destino.stat().st_size == 0:
            raise ErroDeMedicao(
                f"pytest não gerou relatório (rc={saida.returncode}); abortando "
                "em vez de gravar 0"
            )
        raiz = ET.parse(destino).getroot()
        casos = raiz.findall(".//testcase")
        total = len(casos)
        if total <= 0:
            raise ErroDeMedicao(f"relatório sem casos de teste: {total}")
        return total
    finally:
        destino.unlink(missing_ok=True)


def medir_estrutura() -> dict[str, int | str]:
    sys.path.insert(0, str(RAIZ))
    import app.db.models  # noqa: F401 - registra as tabelas
    from app.db.base import Base
    from app.main import criar_app

    rotas = len(criar_app().openapi()["paths"])
    migrations = sorted(p.name for p in (RAIZ / "alembic" / "versions").glob("*.py"))
    if not rotas or not migrations:
        raise ErroDeMedicao("rotas ou migrations não medidas")
    return {
        "rotas": rotas,
        "tabelas": len(Base.metadata.tables),
        "migrations": len(migrations),
        "head": migrations[-1].split("_")[0],
    }


def montar(estrutura: dict[str, int | str], testes: int) -> str:
    return f"""# Painel (vista derivada)

> Gerado por `python -m scripts.gerar_painel` em 2026-11-26. **Não editar à mão.**
> Fonte de verdade da intenção: `PLANO.md`. Do estado: código + testes medidos agora.

## Baseline medida

| Métrica | Valor |
|---|---|
| Rotas | {estrutura["rotas"]} |
| Tabelas ORM | {estrutura["tabelas"]} |
| Migrations | {estrutura["migrations"]} (head `{estrutura["head"]}`) |
| Testes aprovados | {testes} |
| Municípios no seed | 5571 (IBGE, 27 UFs) |
| Postgres de teste | porta 55434, db `notasbr` |

## Lacunas do documento v10.0

| # | Lacuna | Estado | O que falta |
|---|---|---|---|
| 1 | Drivers NFS-e multi-prefeitura | 🌗 PARCIAL | só padrão nacional; falta URL/leiaute oficial por provedor |
| 2 | Modelos município/credencial/webservice + rotas | ✅ | conectividade no cadastro (sem endpoint real por município) |
| 3 | Transporte SOAP DF-e | ❌ AUSENTE | credenciamento NF-e em GO |
| 4 | `CalculoAudit` | ✅ | — |
| 5 | RFC 7807 / circuit / DLQ / rate limit | 🌗 PARCIAL | injetar circuit no fluxo, admin auth, métrica |
| 6 | Hash SHA-256 de XSD | ✅ | substituir pelo ZIP oficial do Portal Nacional |
| 7 | `Idempotency-Key` por header | ✅ | — |

## Fatias do plano original (F9)

| Fatia | Estado |
|---|---|
| F9.0 Plano canônico | ✅ |
| F9.1 Cotação Melhor Envio real | ⚠️ bloqueado (OAuth do proprietário) |
| F9.2 NF-e XML + XSD + assinatura | ✅ |
| F9.3 SOAP SEFAZ-GO | ⬜ |
| F9.4 Autorização NF-e | ⬜ |
| F9.5 Contingência | ⬜ |
| F9.6 DANFE do nfeProc | ⬜ |

## Estado fiscal por documento

| Documento | Geração | Assinatura | Transmissão | Consulta | PDF |
|---|---|---|---|---|---|
| NFS-e | ✅ | ✅ | ✅ real | ✅ real | ✅ |
| NF-e | ✅ | ✅ | ❌ | ❌ | ✅ |
| NFC-e | ❌ | ❌ | ❌ | ❌ | ✅ |
| CT-e | ❌ | ❌ | ❌ | ❌ | ✅ |
| MDF-e | ❌ | ❌ | ❌ | ❌ | ✅ |

## Bloqueios externos

1. `pip-audit` não instalado (exige ADR pela R9)
2. OAuth do Melhor Envio (só o proprietário)
3. Credenciamento NF-e em Goiás
4. Modelo de admin auth (**decisão do proprietário**)
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera o painel medindo o estado real.")
    parser.add_argument("--check", action="store_true", help="compara sem gravar")
    args = parser.parse_args(argv)

    try:
        estrutura = medir_estrutura()
        testes = medir_testes()
    except ErroDeMedicao as exc:
        print(f"erro de medição: {exc}", file=sys.stderr)
        return 2

    conteudo = montar(estrutura, testes)
    if args.check:
        atual = PAINEL.read_text(encoding="utf-8") if PAINEL.is_file() else ""
        if atual != conteudo:
            print("painel divergiu do estado medido", file=sys.stderr)
            return 1
        print("painel em dia")
        return 0

    PAINEL.parent.mkdir(parents=True, exist_ok=True)
    PAINEL.write_text(conteudo, encoding="utf-8")
    print(
        f"painel gravado | rotas {estrutura['rotas']} | tabelas {estrutura['tabelas']} "
        f"| migrations {estrutura['migrations']} | testes {testes}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
