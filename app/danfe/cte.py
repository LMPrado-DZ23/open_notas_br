"""DACTE — DACTE (representação impressa do CT-e) a partir do XML autorizado.

Blocos que o DACTE precisa para conferência:

1. Emitente (transportadora): nome, CNPJ, IE, endereço
2. Remetente, destinatário e tomador (podem ser três pessoas diferentes)
3. Carga e documento originário (chaves das NF-e transportadas)
4. Prestação do serviço (valores) e ICMS
5. Chave de acesso + protocolo

Leiaute exato (medidas, posições) é **[A VALIDAR]** contra o Manual de Orientação
do Contribuinte do CT-e. O que existe aqui é o conteúdo completo em layout
legível e estável.

Regra do produto: **todo campo sai do XML**. O que não estiver no XML imprime
vazio e é listado no rodapé.

[A VALIDAR] O tomador do serviço (`toma`) é opcional no CT-e e muda de
interpretação com `indIEToma` e `toma3`/`toma4`. Quando o grupo não existe,
imprimimos "não informado" em vez de deduzir pelo destinatário — deduzir erra em
CT-e de redespacho.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO

from reportlab.graphics.barcode import code128
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from notasbr.xml_util import local, parse_seguro, texto

ESCURO = colors.HexColor("#111111")
CINZA = colors.HexColor("#e6e6e6")
LINHA = colors.HexColor("#888888")


@dataclass(slots=True)
class DadosDacte:
    chave: str = ""
    protocolo: str = ""
    numero: str = ""
    serie: str = ""
    modelo: str = ""
    emissao: str = ""
    modal: str = ""
    tipo_servico: str = ""
    natureza: str = ""
    ambiente: str = ""
    cfop: str = ""

    emitente_nome: str = ""
    emitente_documento: str = ""
    emitente_ie: str = ""
    emitente_endereco: str = ""
    emitente_municipio_uf: str = ""
    emitente_cep: str = ""

    remetente_nome: str = ""
    remetente_documento: str = ""
    remetente_endereco: str = ""
    remetente_municipio_uf: str = ""

    destinatario_nome: str = ""
    destinatario_documento: str = ""
    destinatario_endereco: str = ""
    destinatario_municipio_uf: str = ""

    tomador_nome: str = ""
    tomador_documento: str = ""

    origem: str = ""
    destino: str = ""
    valor_servico: str = ""
    valor_receber: str = ""
    base_icms: str = ""
    aliquota_icms: str = ""
    valor_icms: str = ""
    valor_carga: str = ""
    produto_predominante: str = ""
    chaves_nfe: list[str] = field(default_factory=list)
    componentes: list[tuple[str, str]] = field(default_factory=list)
    ausentes: list[str] = field(default_factory=list)


MODAIS = {
    "01": "01-Rodoviário",
    "02": "02-Aéreo",
    "03": "03-Aquaviário",
    "04": "04-Ferroviário",
    "05": "05-Dutoviário",
    "06": "06-Multimodal",
}


def _procurar(raiz, *caminhos: str) -> str:
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
    return ""


def _moeda(valor: str) -> str:
    if not valor:
        return ""
    try:
        return f"{Decimal(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (InvalidOperation, ValueError):
        return valor


def _documento(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor)
    if len(digitos) == 14:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    return valor


def _data(valor: str) -> str:
    achado = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", valor)
    if not achado:
        return valor
    ano, mes, dia, hora, minuto = achado.groups()
    return f"{dia}/{mes}/{ano} {hora}:{minuto}"


def _endereco(raiz, prefixo: str) -> tuple[str, str]:
    partes = []
    for campo in ("xLgr", "nro", "xCpl", "xBairro"):
        valor = _procurar(raiz, f"{prefixo}/{campo}")
        if valor:
            partes.append(valor)
    municipio = _procurar(raiz, f"{prefixo}/xMun")
    uf = _procurar(raiz, f"{prefixo}/UF")
    return ", ".join(partes), f"{municipio}/{uf}" if municipio or uf else ""


def extrair_dacte(xml: bytes | str) -> DadosDacte:
    """Extrai os campos do DACTE do XML autorizado do CT-e."""
    dados = xml.encode("utf-8") if isinstance(xml, str) else xml
    raiz = parse_seguro(dados)

    chave = ""
    for elemento in raiz.iter():
        if local(elemento.tag) == "infCte":
            identificador = elemento.get("Id") or ""
            chave = identificador[3:] if identificador.startswith("CTe") else identificador
            break

    emitente_endereco, emitente_municipio_uf = _endereco(raiz, "CTe/infCte/emit/enderEmit")
    remetente_endereco, remetente_municipio_uf = _endereco(raiz, "CTe/infCte/rem/enderReme")
    destinatario_endereco, destinatario_municipio_uf = _endereco(raiz, "CTe/infCte/dest/enderDest")

    modal = _procurar(raiz, "CTe/infCte/ide/modal")
    dados_dacte = DadosDacte(
        chave=chave,
        protocolo=_procurar(raiz, "protCTe/infProt/nProt"),
        numero=_procurar(raiz, "CTe/infCte/ide/nCT"),
        serie=_procurar(raiz, "CTe/infCte/ide/serie"),
        modelo=_procurar(raiz, "CTe/infCte/ide/mod"),
        emissao=_data(_procurar(raiz, "CTe/infCte/ide/dhEmi")),
        modal=MODAIS.get(modal, modal),
        tipo_servico=_procurar(raiz, "CTe/infCte/ide/tpServ"),
        natureza=_procurar(raiz, "CTe/infCte/ide/natOp"),
        ambiente=_procurar(raiz, "CTe/infCte/ide/tpAmb"),
        cfop=_procurar(raiz, "CTe/infCte/ide/CFOP"),
        emitente_nome=_procurar(raiz, "CTe/infCte/emit/xNome"),
        emitente_documento=_documento(
            _procurar(raiz, "CTe/infCte/emit/CNPJ") or _procurar(raiz, "CTe/infCte/emit/CPF")
        ),
        emitente_ie=_procurar(raiz, "CTe/infCte/emit/IE"),
        emitente_endereco=emitente_endereco,
        emitente_municipio_uf=emitente_municipio_uf,
        emitente_cep=_procurar(raiz, "CTe/infCte/emit/enderEmit/CEP"),
        remetente_nome=_procurar(raiz, "CTe/infCte/rem/xNome"),
        remetente_documento=_documento(
            _procurar(raiz, "CTe/infCte/rem/CNPJ") or _procurar(raiz, "CTe/infCte/rem/CPF")
        ),
        remetente_endereco=remetente_endereco,
        remetente_municipio_uf=remetente_municipio_uf,
        destinatario_nome=_procurar(raiz, "CTe/infCte/dest/xNome"),
        destinatario_documento=_documento(
            _procurar(raiz, "CTe/infCte/dest/CNPJ") or _procurar(raiz, "CTe/infCte/dest/CPF")
        ),
        destinatario_endereco=destinatario_endereco,
        destinatario_municipio_uf=destinatario_municipio_uf,
        tomador_nome=_procurar(raiz, "CTe/infCte/toma4/xNome", "CTe/infCte/toma3/xNome"),
        tomador_documento=_documento(
            _procurar(raiz, "CTe/infCte/toma4/CNPJ", "CTe/infCte/toma4/CPF")
        ),
        origem=_procurar(raiz, "CTe/infCte/ide/xMunIni") or _procurar(raiz, "CTe/infCte/ide/UFIni"),
        destino=_procurar(raiz, "CTe/infCte/ide/xMunFim")
        or _procurar(raiz, "CTe/infCte/ide/UFFim"),
        valor_servico=_moeda(_procurar(raiz, "CTe/infCte/vPrest/vTPrest")),
        valor_receber=_moeda(_procurar(raiz, "CTe/infCte/vPrest/vRec")),
        base_icms=_moeda(_procurar(raiz, "CTe/infCte/imp/ICMS/ICMS00/vBC")),
        aliquota_icms=_procurar(raiz, "CTe/infCte/imp/ICMS/ICMS00/pICMS"),
        valor_icms=_moeda(_procurar(raiz, "CTe/infCte/imp/ICMS/ICMS00/vICMS")),
        valor_carga=_moeda(_procurar(raiz, "CTe/infCte/infCTeNorm/infCarga/vCarga")),
        produto_predominante=_procurar(raiz, "CTe/infCte/infCTeNorm/infCarga/proPred"),
    )

    # Componentes do valor (frete peso, pedágio, etc.)
    for elemento in raiz.iter():
        if local(elemento.tag) != "Comp":
            continue
        nome = _procurar(elemento, "xNome")
        valor = _moeda(_procurar(elemento, "vComp"))
        if nome:
            dados_dacte.componentes.append((nome, valor))

    # Chaves das NF-e transportadas
    for elemento in raiz.iter():
        if local(elemento.tag) != "infNFe":
            continue
        chave_nfe = _procurar(elemento, "chave")
        if chave_nfe:
            dados_dacte.chaves_nfe.append(chave_nfe)

    obrigatorios = {
        "chave": dados_dacte.chave,
        "numero": dados_dacte.numero,
        "emitente_nome": dados_dacte.emitente_nome,
        "destinatario_nome": dados_dacte.destinatario_nome,
        "valor_servico": dados_dacte.valor_servico,
        "protocolo": dados_dacte.protocolo,
    }
    dados_dacte.ausentes = [campo for campo, valor in obrigatorios.items() if not valor]
    return dados_dacte


def gerar_dacte(dados: DadosDacte) -> bytes:
    """Gera o DACTE em PDF (A4 paisagem)."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
    pdf.setTitle(f"DACTE {dados.chave}")

    largura, altura = landscape(A4)
    margem = 8 * mm
    util = largura - 2 * margem
    y = altura - margem

    pdf.setFont("Helvetica-Bold", 12)
    pdf.setFillColor(ESCURO)
    pdf.drawString(margem, y, "DACTE")
    pdf.setFont("Helvetica", 6.6)
    pdf.drawString(
        margem,
        y - 4 * mm,
        "Documento Auxiliar do Conhecimento de Transporte Eletrônico — "
        "o XML autorizado prevalece sobre este impresso",
    )
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawRightString(
        largura - margem, y, f"CT-e {dados.numero}  Série {dados.serie}  Modelo {dados.modelo}"
    )
    pdf.setFont("Helvetica", 7)
    pdf.drawRightString(largura - margem, y - 4 * mm, f"Modal {dados.modal}   {dados.emissao}")
    y -= 9 * mm

    pdf.setFont("Helvetica", 6.2)
    pdf.setFillColor(colors.HexColor("#555555"))
    pdf.drawString(margem, y, "CHAVE DE ACESSO")
    pdf.setFont("Helvetica-Bold", 7)
    pdf.setFillColor(ESCURO)
    pdf.drawString(margem + 26 * mm, y, dados.chave or "—")
    pdf.setFont("Helvetica", 6.2)
    pdf.setFillColor(colors.HexColor("#555555"))
    pdf.drawString(margem + 150 * mm, y, "PROTOCOLO")
    pdf.setFont("Helvetica-Bold", 7)
    pdf.setFillColor(ESCURO)
    pdf.drawString(margem + 170 * mm, y, dados.protocolo or "—")
    y -= 4 * mm
    if dados.chave:
        barra = code128.Code128(dados.chave, barHeight=7 * mm, barWidth=0.4)
        barra.drawOn(pdf, margem, y - 7 * mm)
        y -= 9 * mm

    def bloco(titulo: str, linhas: list[tuple[str, str]], altura_bloco: float) -> None:
        nonlocal y
        pdf.setFillColor(CINZA)
        pdf.rect(margem, y - 4.2 * mm, util, 4.6 * mm, fill=1, stroke=0)
        pdf.setFillColor(ESCURO)
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawString(margem + 1.5 * mm, y - 3.1 * mm, titulo)
        y -= 6 * mm
        topo = y + 2 * mm
        for rotulo, valor in linhas:
            if not valor:
                continue
            pdf.setFont("Helvetica", 6)
            pdf.setFillColor(colors.HexColor("#555555"))
            pdf.drawString(margem + 1.5 * mm, y, rotulo)
            pdf.setFont("Helvetica-Bold", 7.2)
            pdf.setFillColor(ESCURO)
            pdf.drawString(margem + 32 * mm, y, valor[:170])
            y -= 3.5 * mm
        pdf.setStrokeColor(LINHA)
        pdf.rect(
            margem, topo - altura_bloco * mm + 2 * mm, util, altura_bloco * mm, fill=0, stroke=1
        )
        y -= 3 * mm

    bloco(
        "EMITENTE (TRANSPORTADORA)",
        [
            ("NOME/RAZÃO SOCIAL", dados.emitente_nome),
            ("CNPJ/CPF", dados.emitente_documento),
            ("INSCRIÇÃO ESTADUAL", dados.emitente_ie),
            ("ENDEREÇO", dados.emitente_endereco),
            ("MUNICÍPIO/UF", f"{dados.emitente_municipio_uf}  CEP {dados.emitente_cep}".strip()),
        ],
        26,
    )
    bloco(
        "REMETENTE / DESTINATÁRIO / TOMADOR",
        [
            ("REMETENTE", dados.remetente_nome),
            ("CNPJ/CPF", dados.remetente_documento),
            ("ENDEREÇO", dados.remetente_endereco),
            ("DESTINATÁRIO", dados.destinatario_nome),
            ("CNPJ/CPF", dados.destinatario_documento),
            (
                "ENDEREÇO",
                f"{dados.destinatario_endereco} {dados.destinatario_municipio_uf}".strip(),
            ),
            (
                "TOMADOR DO SERVIÇO",
                dados.tomador_nome or "não informado no CT-e (o grupo toma é opcional)",
            ),
        ],
        32,
    )
    bloco(
        "CARGA E DOCUMENTO ORIGINÁRIO",
        [
            ("VALOR DA CARGA", dados.valor_carga),
            ("PRODUTO PREDOMINANTE", dados.produto_predominante),
            ("ORIGEM", dados.origem),
            ("DESTINO", dados.destino),
            (
                "CHAVES DAS NF-e",
                ", ".join(dados.chaves_nfe) or "nenhuma chave informada no XML",
            ),
        ],
        26,
    )
    bloco(
        "PRESTAÇÃO DO SERVIÇO",
        [
            ("VALOR DO SERVIÇO", dados.valor_servico),
            ("VALOR A RECEBER", dados.valor_receber),
            ("NATUREZA DA OPERAÇÃO", dados.natureza),
            ("CFOP", dados.cfop),
            (
                "COMPONENTES DO VALOR",
                "; ".join(f"{nome}: {valor}" for nome, valor in dados.componentes),
            ),
        ],
        26,
    )
    bloco(
        "ICMS",
        [
            ("BASE DE CÁLCULO", dados.base_icms),
            ("ALÍQUOTA", dados.aliquota_icms),
            ("VALOR DO ICMS", dados.valor_icms),
        ],
        16,
    )

    pdf.setFont("Helvetica", 5.8)
    pdf.setFillColor(colors.HexColor("#666666"))
    pdf.drawString(
        margem,
        5 * mm,
        "Gerado localmente por open_notas_br. Leiaute [A VALIDAR] contra o MOC do CT-e; "
        "o XML autorizado prevalece.",
    )
    if dados.ausentes:
        pdf.drawString(
            margem,
            2.5 * mm,
            f"Campos não encontrados no XML: {', '.join(dados.ausentes)}",
        )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
