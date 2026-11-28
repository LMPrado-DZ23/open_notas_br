"""Motor de auditoria: detecta o documento, prepara o contexto e roda as regras.

Garantia central: **uma regra que quebra não produz aprovação silenciosa**. A
falha é convertida em achado ``MOTOR-001`` com severidade de erro, de modo que o
relatório nunca diz "aprovado" por causa de um bug.
"""

from __future__ import annotations

import hashlib
import time
import traceback
from pathlib import Path
from xml.etree import ElementTree as ET

from .cadastros import formatar_cnpj, formatar_cpf
from .chave import AMBIENTES, ChaveAcesso
from .erros import DocumentoNaoSuportado
from .modelos import Relatorio
from .regras import regras_para
from .regras.base import Contexto
from .xml_util import LIMITE_PADRAO_BYTES, local, navegar, parse_seguro, texto

#: Raiz aceita -> (tipo interno, nome do corpo)
RAIZES: dict[str, tuple[str, str]] = {
    "nfeProc": ("nfe", "infNFe"),
    "NFe": ("nfe", "infNFe"),
    "cteProc": ("cte", "infCte"),
    "CTe": ("cte", "infCte"),
}

#: Raízes conhecidas que deliberadamente não são auditadas nesta versão.
RAIZES_NAO_AUDITADAS: dict[str, str] = {
    "enviNFe": "lote de envio: audite cada NFe individualmente",
    "retEnviNFe": "retorno de lote: sem documento fiscal para auditar",
    "procEventoNFe": "evento (cancelamento, CC-e): não é documento fiscal nesta versão",
    "evento": "evento: não é documento fiscal nesta versão",
    "retEvento": "retorno de evento: não é documento fiscal",
    "inutNFe": "pedido de inutilização: não é documento fiscal",
    "retConsReciNFe": "retorno de recibo: sem documento fiscal para auditar",
    "consStatServ": "consulta de status de serviço: sem documento fiscal",
}

LIMITACOES_PADRAO: tuple[str, ...] = (
    "Não valida contra o XSD oficial da SEFAZ. A conferência de estrutura é curada, "
    "não é schema validation.",
    "Não valida cadeia ICP-Brasil, revogação nem autenticidade do certificado do "
    "assinante. Só confronta a assinatura com o certificado embutido no documento.",
    "Não acessa a SEFAZ. Não confirma autorização, cancelamento ou denegação na base oficial.",
    "NFS-e (municipal ou padrão nacional) não é auditada nesta versão.",
    "Tabelas de NCM e a classificação fiscal da operação não são conferidas contra a "
    "legislação vigente.",
    "Não avalia idoneidade do emitente, sonegação, fraude ou crédito tributário.",
    "Valores são comparados com tolerância de 1 centavo; divergência acima disso é "
    "apontada, mas a decisão sobre o documento é humana.",
)


def _detectar(raiz: ET.Element) -> tuple[str, str]:
    """Devolve ``(tipo, nome_do_corpo)`` ou levanta DocumentoNaoSuportado."""
    nome = local(raiz.tag)
    if nome in RAIZES:
        return RAIZES[nome]
    if nome in RAIZES_NAO_AUDITADAS:
        raise DocumentoNaoSuportado(f"raiz {nome!r} não é auditada: {RAIZES_NAO_AUDITADAS[nome]}")
    suportadas = ", ".join(sorted(RAIZES))
    raise DocumentoNaoSuportado(
        f"raiz {nome!r} não é um documento fiscal suportado. Raízes aceitas: {suportadas}"
    )


def _chave_do_documento(raiz: ET.Element, tipo: str) -> str | None:
    """Extrai a chave do atributo Id ou, na falta dele, do protocolo."""
    prefixo = "NFe" if tipo == "nfe" else "CTe"
    nome_corpo = "infNFe" if tipo == "nfe" else "infCte"

    corpo = None
    for elemento in raiz.iter():
        if local(elemento.tag) == nome_corpo:
            corpo = elemento
            break

    if corpo is not None:
        bruto = corpo.get("Id")
        if bruto:
            candidata = bruto[len(prefixo) :] if bruto.startswith(prefixo) else bruto
            return candidata or None

    no_protocolo = "protNFe/infProt/chNFe" if tipo == "nfe" else "protCTe/infProt/chCTe"
    do_protocolo = texto(navegar(raiz, no_protocolo))
    return do_protocolo or None


def _resumo_emitente(corpo: ET.Element) -> dict[str, object]:
    emitente = navegar(corpo, "emit")
    if emitente is None:
        return {}
    cnpj = texto(navegar(emitente, "CNPJ"))
    cpf = texto(navegar(emitente, "CPF"))
    dados: dict[str, object] = {}
    if cnpj:
        dados["cnpj"] = formatar_cnpj(cnpj)
    elif cpf:
        dados["cpf"] = formatar_cpf(cpf)
    nome = texto(navegar(emitente, "xNome"))
    if nome:
        dados["nome"] = nome
    uf = texto(navegar(emitente, "enderEmit/UF"))
    if uf:
        dados["uf"] = uf
    ie = texto(navegar(emitente, "IE"))
    if ie:
        dados["ie"] = ie
    crt = texto(navegar(emitente, "CRT"))
    if crt:
        dados["crt"] = crt
    return dados


def _resumo_destinatario(corpo: ET.Element) -> dict[str, object]:
    destinatario = navegar(corpo, "dest")
    if destinatario is None:
        return {}
    dados: dict[str, object] = {}
    cnpj = texto(navegar(destinatario, "CNPJ"))
    cpf = texto(navegar(destinatario, "CPF"))
    estrangeiro = texto(navegar(destinatario, "idEstrangeiro"))
    if cnpj:
        dados["cnpj"] = formatar_cnpj(cnpj)
    elif cpf:
        dados["cpf"] = formatar_cpf(cpf)
    elif estrangeiro:
        dados["id_estrangeiro"] = estrangeiro
    nome = texto(navegar(destinatario, "xNome"))
    if nome:
        dados["nome"] = nome
    uf = texto(navegar(destinatario, "enderDest/UF"))
    if uf:
        dados["uf"] = uf
    return dados


def _valor_total(corpo: ET.Element, tipo: str) -> str | None:
    from .xml_util import decimal as _dec
    from .xml_util import dinheiro

    if tipo == "nfe":
        return dinheiro(_dec(texto(navegar(corpo, "total/ICMSTot/vNF"))))
    return dinheiro(_dec(texto(navegar(corpo, "vPrest/vTPrest"))))


def _preparar_contexto(
    raiz: ET.Element,
    tipo: str,
    nome_corpo: str,
    arquivo: str | None,
    bytes_originais: bytes | None = None,
) -> Contexto:
    corpo = navegar(raiz, nome_corpo)
    if corpo is None:
        # Pode estar aninhado (nfeProc/NFe/infNFe), então procure em qualquer nível.
        for elemento in raiz.iter():
            if local(elemento.tag) == nome_corpo:
                corpo = elemento
                break
    if corpo is None:
        raise DocumentoNaoSuportado(
            f"documento {local(raiz.tag)!r} não contém {nome_corpo}: estrutura mínima ausente"
        )

    chave = _chave_do_documento(raiz, tipo)
    chave_parseada: ChaveAcesso | None = None
    if chave and len(chave) == 44 and chave.isdigit():
        try:
            chave_parseada = ChaveAcesso.parse(chave)
        except Exception:  # DV inválido: a regra CHAVE-DV-001 reporta
            chave_parseada = None

    versao = corpo.get("versao") or raiz.get("versao")
    contexto = Contexto(
        raiz=raiz,
        tipo=tipo,
        corpo=corpo,
        ns=None,
        versao_layout=versao,
        chave=chave,
        chave_parseada=chave_parseada,
        arquivo=arquivo,
        bytes_originais=bytes_originais,
    )
    from .xml_util import namespace as _ns

    contexto.ns = _ns(raiz.tag)

    tp_amb = texto(navegar(corpo, "ide/tpAmb"))
    ambiente = AMBIENTES.get(tp_amb) if tp_amb else None
    contexto.extras = {
        "emitente": _resumo_emitente(corpo),
        "destinatario": _resumo_destinatario(corpo),
        "valor_total": _valor_total(corpo, tipo),
        "ambiente": ambiente,
    }
    return contexto


def auditar_bytes(
    dados: bytes,
    *,
    arquivo: str | None = None,
    limite_bytes: int = LIMITE_PADRAO_BYTES,
) -> Relatorio:
    """Audita um XML em memória.

    Levanta :class:`~notasbr.erros.XmlInvalido` se os bytes não forem XML legível,
    :class:`~notasbr.erros.ArquivoGrandeDemais` acima do limite e
    :class:`~notasbr.erros.DocumentoNaoSuportado` se a raiz não for um documento
    fiscal auditável.
    """
    inicio = time.perf_counter()
    raiz = parse_seguro(dados, limite=limite_bytes)
    tipo, nome_corpo = _detectar(raiz)
    contexto = _preparar_contexto(raiz, tipo, nome_corpo, arquivo, bytes_originais=dados)

    regras = regras_para(tipo)
    for definicao in regras:
        try:
            definicao.funcao(contexto)
        except Exception as exc:
            contexto.erro(
                "MOTOR-001",
                f"a regra {definicao.codigo} falhou ao ser avaliada: {type(exc).__name__}: {exc}",
                "",
                regra=definicao.codigo,
                excecao=type(exc).__name__,
                traceback="".join(traceback.format_exception_only(type(exc), exc)).strip(),
            )

    relatorio = Relatorio(
        tipo=tipo,
        raiz=local(raiz.tag),
        versao_layout=contexto.versao_layout,
        chave=contexto.chave,
        arquivo=arquivo,
        sha256=hashlib.sha256(dados).hexdigest(),
        modelo=contexto.chave_parseada.modelo_nome if contexto.chave_parseada else None,
        ambiente=contexto.extras.get("ambiente"),
        emitente=contexto.extras.get("emitente") or {},
        destinatario=contexto.extras.get("destinatario") or {},
        valor_total=contexto.extras.get("valor_total"),
        achados=contexto.achados,
        puladas=contexto.puladas,
        limitacoes=list(LIMITACOES_PADRAO),
        regras_avaliadas=len(regras),
        duracao_ms=(time.perf_counter() - inicio) * 1000,
    )
    return relatorio


def auditar_arquivo(caminho: str | Path, *, limite_bytes: int = LIMITE_PADRAO_BYTES) -> Relatorio:
    """Lê o arquivo e audita. O nome do arquivo vai no relatório, não o caminho absoluto."""
    caminho = Path(caminho)
    dados = caminho.read_bytes()
    return auditar_bytes(dados, arquivo=caminho.name, limite_bytes=limite_bytes)


__all__ = [
    "LIMITACOES_PADRAO",
    "RAIZES",
    "RAIZES_NAO_AUDITADAS",
    "auditar_arquivo",
    "auditar_bytes",
]
