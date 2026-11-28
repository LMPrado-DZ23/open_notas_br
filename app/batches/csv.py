"""Leitura e validação de CSV de lote.

Formato aceito (cabeçalho obrigatório, ordem livre)::

    idempotency_key,valor,descricao,competencia,tomador_nome,tomador_documento

Decisões que evitam lote pela metade:

- **Cabeçalho é obrigatório.** Sem ele, a primeira linha de dados seria consumida
  como cabeçalho e o lote sairia com uma nota a menos, sem erro.
- **Linha inválida não derruba o lote**: entra no relatório com o motivo. O
  usuário precisa saber *qual* linha falhou, e o resto deve ser processado.
- **Duplicata de `idempotency_key` dentro do arquivo é recusada na leitura.** Duas
  linhas com a mesma chave seriam a mesma nota; processar as duas gera relatório
  mentiroso (uma sucesso, outra "já existe"), quando o certo é apontar o erro de
  origem.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

COLUNAS_OBRIGATORIAS = ("idempotency_key", "valor", "descricao")
COLUNAS_OPCIONAIS = ("competencia", "tomador_nome", "tomador_documento")
CODIFICACOES = ("utf-8-sig", "utf-8", "cp1252")


class CsvInvalido(Exception):
    """Arquivo ilegível ou sem cabeçalho mínimo."""


@dataclass(slots=True)
class LinhaLote:
    """Uma linha pronta para emitir, ou com o motivo da recusa."""

    numero_linha: int
    idempotency_key: str = ""
    valor: Decimal | None = None
    descricao: str = ""
    competencia: str | None = None
    tomador_nome: str | None = None
    tomador_documento: str | None = None
    erro: str | None = None

    @property
    def valida(self) -> bool:
        return self.erro is None


@dataclass(slots=True)
class LoteLido:
    """Resultado da leitura: linhas válidas e recusadas, no total."""

    linhas: list[LinhaLote] = field(default_factory=list)
    erros_de_arquivo: list[str] = field(default_factory=list)

    @property
    def validas(self) -> list[LinhaLote]:
        return [linha for linha in self.linhas if linha.valida]

    @property
    def invalidas(self) -> list[LinhaLote]:
        return [linha for linha in self.linhas if not linha.valida]

    @property
    def total(self) -> int:
        return len(self.linhas)


def _decodificar(conteudo: bytes) -> str:
    for codificacao in CODIFICACOES:
        try:
            return conteudo.decode(codificacao)
        except UnicodeDecodeError:
            continue
    raise CsvInvalido("não foi possível decodificar o arquivo; salve como UTF-8 ou CSV do Excel")


def _limpar(valor: str | None) -> str:
    return (valor or "").strip()


def _converter_valor(bruto: str) -> Decimal | None:
    """Converte valor monetário aceitando os dois padrões de separador.

    Regra: se há vírgula E ponto, o ponto é milhar e a vírgula é decimal
    (`1.234,56`). Se há só vírgula, ela é decimal (`100,50`). Se há só ponto, ele é
    decimal (`100.00`) — que é o padrão de CSV exportado por sistema.

    A versão anterior removia todo ponto, e `100.00` virava `10000`: dez vezes o
    valor da nota. Erro silencioso e caro, pego por teste.
    """
    texto = _limpar(bruto)
    if not texto:
        return None
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def _validar(linha: LinhaLote) -> None:
    """Preenche `erro` com o primeiro problema encontrado."""
    if not linha.idempotency_key:
        linha.erro = "idempotency_key vazia"
        return
    if len(linha.idempotency_key) < 8:
        linha.erro = "idempotency_key deve ter ao menos 8 caracteres"
        return
    if not linha.descricao:
        linha.erro = "descricao vazia"
        return
    if linha.valor is None:
        linha.erro = "valor ausente ou inválido"
        return
    if linha.valor <= 0:
        linha.erro = "valor deve ser maior que zero"
        return
    # Mais de duas casas indica separador mal interpretado. Em CSV com vírgula
    # decimal o valor precisa estar entre aspas ("1.234,56"); sem aspas o campo é
    # cortado no meio e o valor sairia errado sem aviso.
    if -linha.valor.as_tuple().exponent > 2:  # type: ignore[operator]
        linha.erro = (
            "valor com mais de 2 casas decimais: se usa vírgula decimal, "
            'coloque o campo entre aspas ("1.234,56")'
        )
        return
    if linha.competencia and (len(linha.competencia) != 7 or linha.competencia[4] != "-"):
        linha.erro = "competência deve ser AAAA-MM"
        return


def ler_csv(conteudo: bytes) -> LoteLido:
    """Lê o CSV e devolve linhas válidas e recusadas."""
    texto = _decodificar(conteudo)
    leitor = csv.DictReader(io.StringIO(texto))
    if not leitor.fieldnames:
        raise CsvInvalido("arquivo CSV vazio: nenhum cabeçalho encontrado")

    cabecalho = {nome.strip().lower() for nome in leitor.fieldnames if nome}
    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in cabecalho]
    if faltando:
        raise CsvInvalido(
            f"cabeçalho sem coluna(s) obrigatória(s): {', '.join(faltando)}. "
            f"Esperado: {', '.join(COLUNAS_OBRIGATORIAS + COLUNAS_OPCIONAIS)}"
        )

    lote = LoteLido()
    vistos: dict[str, int] = {}

    for indice, bruto in enumerate(leitor, start=2):  # linha 1 é o cabeçalho
        registro = {(_limpar(k).lower()): _limpar(v) for k, v in bruto.items() if k}

        # Linha totalmente vazia (comum no fim do arquivo do Excel) é ignorada.
        if not any(registro.values()):
            continue

        valor = _converter_valor(registro.get("valor", ""))

        linha = LinhaLote(
            numero_linha=indice,
            idempotency_key=registro.get("idempotency_key", ""),
            valor=valor,
            descricao=registro.get("descricao", ""),
            competencia=registro.get("competencia") or None,
            tomador_nome=registro.get("tomador_nome") or None,
            tomador_documento=registro.get("tomador_documento") or None,
        )

        if linha.idempotency_key and linha.idempotency_key in vistos:
            linha.erro = (
                f"idempotency_key repetida (já usada na linha {vistos[linha.idempotency_key]})"
            )
        else:
            # `_validar` roda SEMPRE: antes ele só era chamado quando havia chave, então
            # linha sem `idempotency_key` passava como válida e ia para o banco com chave
            # vazia — todas colidindo na busca de idempotência depois.
            if linha.idempotency_key:
                vistos[linha.idempotency_key] = indice
            _validar(linha)

        lote.linhas.append(linha)

    if not lote.linhas:
        raise CsvInvalido("o arquivo não tem nenhuma linha de dados")
    return lote
