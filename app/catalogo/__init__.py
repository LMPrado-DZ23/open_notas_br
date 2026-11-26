"""Importação de endpoints fiscais com procedência obrigatória.

Para suportar "todas as SEFAZ" e "todas as prefeituras" é preciso ingerir centenas de
endpoints. O risco não é digitar URL errada: é **inventar** uma URL plausível e o sistema
passar a emitir contra ela. Por isso a importação recusa qualquer linha sem `fonte_url`
https — a URL só entra se for possível mostrar de onde veio.

Este módulo não contém **nenhum** endpoint. Ele valida e grava os que vierem de fora, com
`--dry-run` mostrando o plano antes de tocar no banco.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

#: As 27 UFs. Recusa qualquer outra sigla — erro de digitação viraria endpoint órfão.
#: Modelos suportados no catálogo. 55 NF-e, 65 NFC-e, 57 CT-e, 58 MDF-e.
MODELOS = frozenset({"55", "65", "57", "58"})

UFS = (
    "AC",
    "AL",
    "AM",
    "AP",
    "BA",
    "CE",
    "DF",
    "ES",
    "GO",
    "MA",
    "MG",
    "MS",
    "MT",
    "PA",
    "PB",
    "PE",
    "PI",
    "PR",
    "RJ",
    "RN",
    "RO",
    "RR",
    "RS",
    "SC",
    "SE",
    "SP",
    "TO",
)


class ErroDeImportacao(Exception):
    """Linha inválida. A mensagem diz qual linha e por quê."""


@dataclass(slots=True)
class LinhaEndpoints:
    """Uma linha do arquivo de endpoints, já validada."""

    uf: str
    ambiente: str
    servico: str
    url: str
    versao_soap: str
    fonte_url: str
    modelo: str = "55"
    autorizador: str | None = None
    versao_layout: str | None = None


@dataclass(slots=True)
class Plano:
    """Resultado de uma importação (ou do seu `dry-run`)."""

    inserir: list[Any] = field(default_factory=list)
    atualizar: list[Any] = field(default_factory=list)
    inalterado: list[Any] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.inserir) + len(self.atualizar) + len(self.inalterado)


def _exigir_https(campo: str, valor: str, linha: int) -> None:
    if not valor.startswith("https://"):
        raise ErroDeImportacao(
            f"linha {linha}: {campo} precisa começar com https:// (recebido {valor!r})"
        )


def validar_linha(bruta: dict[str, Any], *, linha: int) -> LinhaEndpoints:
    """Valida uma linha crua. Erro aqui é barato; erro no banco é caro."""
    try:
        uf = str(bruta["uf"]).upper().strip()
        ambiente = str(bruta["ambiente"]).strip()
        servico = str(bruta["servico"]).strip()
        url = str(bruta["url"]).strip()
        versao_soap = str(bruta.get("versao_soap", "1.2")).strip()
        fonte = str(bruta["fonte_url"]).strip()
    except KeyError as exc:
        raise ErroDeImportacao(f"linha {linha}: campo obrigatório ausente: {exc}") from exc

    if uf not in UFS:
        raise ErroDeImportacao(f"linha {linha}: UF inválida: {uf!r}")
    if ambiente not in ("1", "2"):
        raise ErroDeImportacao(
            f"linha {linha}: ambiente precisa ser '1' (produção) ou '2' (homologação), "
            f"recebido {ambiente!r}"
        )
    modelo = str(bruta.get("modelo", "55")).strip()
    if modelo not in MODELOS:
        raise ErroDeImportacao(
            f"linha {linha}: modelo inválido {modelo!r}; válidos: {sorted(MODELOS)}"
        )

    if versao_soap not in ("1.1", "1.2"):
        raise ErroDeImportacao(f"linha {linha}: versao_soap inválida: {versao_soap!r}")

    from app.db.models.webservice_sefaz import ServicoSefaz

    if servico not in {s.value for s in ServicoSefaz}:
        raise ErroDeImportacao(
            f"linha {linha}: serviço desconhecido: {servico!r}. "
            f"Válidos: {sorted(s.value for s in ServicoSefaz)}"
        )

    _exigir_https("url", url, linha)
    _exigir_https("fonte_url", fonte, linha)

    return LinhaEndpoints(
        uf=uf,
        modelo=modelo,
        ambiente=ambiente,
        servico=servico,
        url=url,
        versao_soap=versao_soap,
        fonte_url=fonte,
        autorizador=(str(bruta["autorizador"]).strip() if bruta.get("autorizador") else None),
        versao_layout=(str(bruta["versao_layout"]).strip() if bruta.get("versao_layout") else None),
    )


def validar_lote(brutas: Iterable[dict[str, Any]]) -> tuple[list[LinhaEndpoints], list[str]]:
    """Valida o lote inteiro. Devolve (válidas, erros) sem parar no primeiro erro."""
    validas: list[LinhaEndpoints] = []
    erros: list[str] = []
    vistos: dict[tuple[str, str, str], int] = {}

    for indice, bruta in enumerate(brutas, start=1):
        try:
            linha = validar_linha(bruta, linha=indice)
        except ErroDeImportacao as exc:
            erros.append(str(exc))
            continue

        chave = (linha.uf, linha.modelo, linha.ambiente, linha.servico)
        if chave in vistos:
            # Duplicata no mesmo arquivo: qual vence? Nenhuma — o arquivo está ambíguo.
            erros.append(
                f"linha {indice}: (uf={linha.uf}, modelo={linha.modelo}, "
                f"ambiente={linha.ambiente}, "
                f"servico={linha.servico}) repetido (já na linha {vistos[chave]})"
            )
            continue
        vistos[chave] = indice
        validas.append(linha)

    return validas, erros


async def planejar_endpoints_sefaz(sessao: AsyncSession, linhas: list[LinhaEndpoints]) -> Plano:
    """Compara com o banco e classifica: inserir, atualizar, inalterado."""
    from app.db.models.webservice_sefaz import WebserviceSefaz

    plano = Plano()
    for linha in linhas:
        existente = (
            await sessao.execute(
                select(WebserviceSefaz).where(
                    WebserviceSefaz.uf == linha.uf,
                    WebserviceSefaz.modelo == linha.modelo,
                    WebserviceSefaz.ambiente == linha.ambiente,
                    WebserviceSefaz.servico == linha.servico,
                )
            )
        ).scalar_one_or_none()

        if existente is None:
            plano.inserir.append(linha)
        elif (
            existente.url != linha.url
            or existente.fonte_url != linha.fonte_url
            or str(existente.versao_soap) != linha.versao_soap
        ):
            plano.atualizar.append((existente, linha))
        else:
            plano.inalterado.append(linha)
    return plano


async def aplicar_endpoints_sefaz(
    sessao: AsyncSession, plano: Plano, *, dry_run: bool = True
) -> Plano:
    """Grava o plano. `dry_run=True` devolve o plano sem tocar no banco (padrão)."""
    from app.db.models.webservice_sefaz import ServicoSefaz, VersaoSOAP, WebserviceSefaz

    if dry_run:
        return plano

    for linha in plano.inserir:
        sessao.add(
            WebserviceSefaz(
                uf=linha.uf,
                modelo=linha.modelo,
                ambiente=linha.ambiente,
                servico=ServicoSefaz(linha.servico),
                url=linha.url,
                versao_soap=VersaoSOAP(linha.versao_soap),
                versao_layout=linha.versao_layout,
                fonte_url=linha.fonte_url,
                autorizador=linha.autorizador,
            )
        )

    for existente, linha in plano.atualizar:
        existente.url = linha.url
        existente.fonte_url = linha.fonte_url
        existente.versao_soap = VersaoSOAP(linha.versao_soap)
        existente.versao_layout = linha.versao_layout
        existente.autorizador = linha.autorizador

    await sessao.flush()
    return plano


@dataclass(frozen=True, slots=True)
class Cobertura:
    """Quanto do território está realmente configurado. Medido, não estimado."""

    ufs_com_autorizacao: tuple[str, ...]
    ufs_sem_autorizacao: tuple[str, ...]

    @property
    def percentual(self) -> float:
        total = len(self.ufs_com_autorizacao) + len(self.ufs_sem_autorizacao)
        if total == 0:
            return 0.0
        return 100.0 * len(self.ufs_com_autorizacao) / total


async def medir_cobertura(
    sessao: AsyncSession, *, ambiente: str = "2", modelo: str = "55"
) -> Cobertura:
    """Quais UFs têm serviço de autorização cadastrado para (ambiente, modelo).

    `modelo` é obrigatório na prática: 55 e 65 têm conjuntos diferentes de UFs, e somar os
    dois produziria um número que não existe em nenhum dos dois.
    """
    from app.db.models.webservice_sefaz import ServicoSefaz, WebserviceSefaz

    resultado = await sessao.execute(
        select(WebserviceSefaz.uf).where(
            WebserviceSefaz.ambiente == ambiente,
            WebserviceSefaz.modelo == modelo,
            WebserviceSefaz.servico == ServicoSefaz("NFeAutorizacao"),
        )
    )
    configuradas = {str(uf) for uf in resultado.scalars()}
    return Cobertura(
        ufs_com_autorizacao=tuple(sorted(configuradas)),
        ufs_sem_autorizacao=tuple(sorted(set(UFS) - configuradas)),
    )
