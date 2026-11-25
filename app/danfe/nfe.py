"""DANFE Simplificado — modelo etiqueta, a partir do XML autorizado da NF-e.

Layout pedido nas imagens de referência: título, chave em código de barras com o
número em texto, protocolo, emitente com CNPJ/UF/IE, série/número/emissão,
operação 0-ENTRADA ou 1-SAÍDA, destinatário e valor total.

Duas regras que o código respeita:

1. **A chave é o identificador do código de barras**, não o número da nota. É o
   que permite conferência por qualquer leitor.
2. **O XML autorizado prevalece sobre o PDF.** Tudo aqui é lido do XML; nada é
   recalculado.

O leiaute exato (medidas, fontes) é [A VALIDAR] contra o manual vigente. Campos e
ordem seguem as imagens fornecidas pelo solicitante.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO

from reportlab.graphics.barcode import code128
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.danfe.base import TipoRepresentacao
from notasbr.chave import ChaveAcesso, chave_valida
from notasbr.xml_util import local, parse_seguro, texto

LARGURA, ALTURA = A4
MARGEM = 12 * mm
ESCURO = colors.HexColor("#111111")
CINZA = colors.HexColor("#f0f0f0")
LINHA = colors.HexColor("#888888")


@dataclass(slots=True)
class DadosNfe:
    """Campos que o DANFE Simplificado imprime."""

    chave: str = ""
    protocolo: str = ""
    emitente_nome: str = ""
    emitente_cnpj: str = ""
    emitente_uf: str = ""
    emitente_ie: str = ""
    serie: str = ""
    numero: str = ""
    emissao: str = ""
    operacao: str = ""
    destinatario_nome: str = ""
    destinatario_documento: str = ""
    destinatario_ie: str = ""
    destinatario_endereco: str = ""
    destinatario_uf: str = ""
    valor_total: str = ""
    ausentes: list[str] | None = None


def _procurar(raiz, *caminhos: str) -> str | None:
    """Primeiro valor encontrado entre caminhos de nomes locais."""
    for caminho in caminhos:
        atual = raiz
        achou = True
        for parte in caminho.split("/"):
            proximo = None
            for filho in atual:
                if local(filho.tag) == parte:
                    proximo = filho
                    break
            if proximo is None:
                achou = False
                break
            atual = proximo
        if achou:
            valor = texto(atual)
            if valor:
                return valor
    return None


def _formatar_documento(valor: str) -> str:
    if len(valor) == 14:
        return f"{valor[:2]}.{valor[2:5]}.{valor[5:8]}/{valor[8:12]}-{valor[12:]}"
    if len(valor) == 11:
        return f"{valor[:3]}.{valor[3:6]}.{valor[6:9]}-{valor[9:]}"
    return valor


def _formatar_data(valor: str) -> str:
    """ISO (AAAA-MM-DD...) para DD/MM/AAAA."""
    achado = re.match(r"(\d{4})-(\d{2})-(\d{2})", valor)
    if not achado:
        return valor
    ano, mes, dia = achado.groups()
    return f"{dia}/{mes}/{ano}"


def _formatar_moeda(valor: str) -> str:
    from decimal import Decimal, InvalidOperation

    try:
        return f"{Decimal(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (InvalidOperation, ValueError):
        return valor


def extrair_nfe(xml: bytes | str) -> DadosNfe:
    """Extrai os campos do DANFE Simplificado do XML da NF-e."""
    dados = xml.encode("utf-8") if isinstance(xml, str) else xml
    raiz = parse_seguro(dados)

    # A chave vem do atributo Id de infNFe (prefixo "NFe" removido), não de
    # caminho de elemento: atributo não é navegável por nome local.
    identificador = ""
    for elemento in raiz.iter():
        if local(elemento.tag) == "infNFe":
            identificador = elemento.get("Id") or ""
            break
    chave = identificador[3:] if identificador.startswith("NFe") else identificador

    dados_nfe = DadosNfe(
        chave=chave,
        protocolo=_procurar(raiz, "protNFe/infProt/nProt") or "",
        emitente_nome=_procurar(raiz, "NFe/infNFe/emit/xNome") or "",
        emitente_cnpj=_formatar_documento(
            _procurar(raiz, "NFe/infNFe/emit/CNPJ") or _procurar(raiz, "NFe/infNFe/emit/CPF") or ""
        ),
        emitente_uf=_procurar(raiz, "NFe/infNFe/emit/enderEmit/UF") or "",
        emitente_ie=_procurar(raiz, "NFe/infNFe/emit/IE") or "",
        serie=_procurar(raiz, "NFe/infNFe/ide/serie") or "",
        numero=_procurar(raiz, "NFe/infNFe/ide/nNF") or "",
        emissao=_formatar_data(_procurar(raiz, "NFe/infNFe/ide/dhEmi") or ""),
        operacao="1-SAÍDA"
        if (_procurar(raiz, "NFe/infNFe/ide/tpNF") or "1") == "1"
        else "0-ENTRADA",
        destinatario_nome=_procurar(raiz, "NFe/infNFe/dest/xNome") or "",
        destinatario_documento=_formatar_documento(
            _procurar(raiz, "NFe/infNFe/dest/CNPJ") or _procurar(raiz, "NFe/infNFe/dest/CPF") or ""
        ),
        destinatario_ie=_procurar(raiz, "NFe/infNFe/dest/IE") or "",
        destinatario_endereco=_montar_endereco(raiz),
        destinatario_uf=_procurar(raiz, "NFe/infNFe/dest/enderDest/UF") or "",
        valor_total=_formatar_moeda(_procurar(raiz, "NFe/infNFe/total/ICMSTot/vNF") or ""),
        ausentes=[],
    )

    obrigatorios = {
        "chave": dados_nfe.chave,
        "emitente_nome": dados_nfe.emitente_nome,
        "numero": dados_nfe.numero,
        "destinatario_nome": dados_nfe.destinatario_nome,
        "valor_total": dados_nfe.valor_total,
        "protocolo": dados_nfe.protocolo,
    }
    dados_nfe.ausentes = [campo for campo, valor in obrigatorios.items() if not valor]
    return dados_nfe


def _montar_endereco(raiz) -> str:
    partes = []
    for campo, rotulo in (
        ("enderDest/xLgr", ""),
        ("enderDest/nro", ""),
        ("enderDest/xCpl", ""),
        ("enderDest/xBairro", ""),
        ("enderDest/xMun", ""),
    ):
        valor = _procurar(raiz, f"NFe/infNFe/dest/{campo}")
        if valor:
            partes.append(f"{rotulo}{valor}".strip())
    return ", ".join(partes)


def _chave_formatada(chave: str) -> str:
    return " ".join(chave[i : i + 4] for i in range(0, len(chave), 4))


def gerar_danfe_simplificado(dados: DadosNfe) -> bytes:
    """Gera o PDF no modelo etiqueta."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(f"DANFE Simplificado {dados.chave}")
    pdf.setAuthor(dados.emitente_nome or "open_notas_br")
    pdf.setSubject("DANFE Simplificado — modelo etiqueta")

    largura_util = LARGURA - 2 * MARGEM
    y = ALTURA - MARGEM

    # Título
    pdf.setFont("Helvetica-Bold", 12)
    pdf.setFillColor(ESCURO)
    pdf.drawCentredString(LARGURA / 2, y, "DANFE SIMPLIFICADO - ETIQUETA")
    y -= 5 * mm
    pdf.setFont("Helvetica", 6)
    pdf.drawCentredString(
        LARGURA / 2,
        y,
        "Documento auxiliar da NF-e — o XML autorizado prevalece sobre este impresso",
    )
    y -= 6 * mm

    # Chave de acesso
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawString(MARGEM, y, "CHAVE DE ACESSO")
    y -= 4 * mm
    if dados.chave:
        pdf.setStrokeColor(LINHA)
        pdf.rect(MARGEM, y - 13 * mm, largura_util, 15 * mm, fill=0, stroke=1)
        codigo = code128.Code128(dados.chave, barHeight=10 * mm, barWidth=0.42)
        codigo.drawOn(pdf, MARGEM + 3 * mm, y - 11.5 * mm)
        pdf.setFont("Helvetica", 7)
        pdf.drawCentredString(LARGURA / 2, y - 14 * mm, _chave_formatada(dados.chave))
    y -= 18 * mm

    # Protocolo
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawString(MARGEM, y, "PROTOCOLO DE AUTORIZAÇÃO DE USO")
    pdf.setFont("Helvetica", 8)
    pdf.drawString(MARGEM + 62 * mm, y, dados.protocolo or "—")
    y -= 5 * mm

    def bloco(titulo: str, linhas: list[tuple[str, str]], altura: float) -> None:
        nonlocal y
        pdf.setFillColor(CINZA)
        pdf.rect(MARGEM, y - 4.6 * mm, largura_util, 5 * mm, fill=1, stroke=0)
        pdf.setFillColor(ESCURO)
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.drawString(MARGEM + 1.5 * mm, y - 3.4 * mm, titulo)
        y -= 6 * mm
        pdf.setFont("Helvetica", 7.5)
        inicio = y + 3 * mm
        for rotulo, valor in linhas:
            if not valor:
                continue
            pdf.setFont("Helvetica", 6.5)
            pdf.setFillColor(colors.HexColor("#555555"))
            pdf.drawString(MARGEM + 1.5 * mm, y, rotulo)
            pdf.setFont("Helvetica-Bold", 7.5)
            pdf.setFillColor(ESCURO)
            pdf.drawString(MARGEM + 34 * mm, y, valor[:100])
            y -= 4 * mm
        pdf.setStrokeColor(LINHA)
        pdf.rect(MARGEM, inicio - altura * mm + 2 * mm, largura_util, altura * mm, fill=0, stroke=1)
        y -= 3 * mm

    bloco(
        "EMITENTE",
        [
            ("NOME/RAZÃO SOCIAL", dados.emitente_nome),
            ("CNPJ", dados.emitente_cnpj),
            ("UF", dados.emitente_uf),
            ("INSCRIÇÃO ESTADUAL", dados.emitente_ie),
        ],
        22,
    )

    bloco(
        "IDENTIFICAÇÃO",
        [
            ("SÉRIE", dados.serie),
            ("NÚMERO", dados.numero),
            ("EMISSÃO", dados.emissao),
            ("OPERAÇÃO", dados.operacao),
        ],
        20,
    )

    bloco(
        "DESTINATÁRIO",
        [
            ("NOME/RAZÃO SOCIAL", dados.destinatario_nome),
            ("CNPJ/CPF", dados.destinatario_documento),
            ("INSCRIÇÃO ESTADUAL", dados.destinatario_ie),
            ("ENDEREÇO", dados.destinatario_endereco),
            ("UF", dados.destinatario_uf),
        ],
        26,
    )

    pdf.setFillColor(CINZA)
    pdf.rect(MARGEM, y - 7 * mm, largura_util, 9 * mm, fill=1, stroke=0)
    pdf.setFillColor(ESCURO)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(MARGEM + 1.5 * mm, y - 4 * mm, "VALOR TOTAL DA NOTA FISCAL")
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawRightString(LARGURA - MARGEM - 2 * mm, y - 4.5 * mm, f"R$ {dados.valor_total}")
    y -= 12 * mm

    pdf.setFont("Helvetica", 5.8)
    pdf.setFillColor(colors.HexColor("#666666"))
    pdf.drawString(
        MARGEM,
        MARGEM + 6 * mm,
        "Gerado localmente por open_notas_br. Leiaute conforme imagens de referência do "
        "solicitante; medidas [A VALIDAR] no manual vigente.",
    )
    if dados.ausentes:
        pdf.drawString(
            MARGEM,
            MARGEM + 3 * mm,
            f"Campos não encontrados no XML: {', '.join(dados.ausentes[:6])}",
        )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


class DanfeSimplificado:
    """Representação `nfe/danfe_simplificado`."""

    tipo = TipoRepresentacao(documento="nfe", formato="danfe_simplificado")

    def gerar(self, xml: bytes) -> bytes:
        return gerar_danfe_simplificado(extrair_nfe(xml))


class Danfse:
    """Representação `nfse/danfse`, delegando ao gerador do módulo DANFSe."""

    tipo = TipoRepresentacao(documento="nfse", formato="danfse")

    def gerar(self, xml: bytes) -> bytes:
        from app.danfse.parser import parse_danfse
        from app.danfse.render import gerar_danfse

        return gerar_danfse(parse_danfse(xml))


def registrar_todas() -> None:
    """Registra as representações disponíveis neste pacote."""
    from app.danfe.base import registrar

    registrar(DanfeSimplificado())
    registrar(Danfse())


__all__ = [
    "ChaveAcesso",
    "DadosNfe",
    "DanfeSimplificado",
    "Danfse",
    "chave_valida",
    "extrair_nfe",
    "gerar_danfe_simplificado",
    "registrar_todas",
]
