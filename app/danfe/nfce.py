"""Cupom / DANFE NFC-e a partir do XML autorizado.

Formato: bobina de 80 mm, uma coluna, para impressora térmica — é como o cupom
sai no balcão. O DANFE NFC-e em A4 existe, mas o caso real de uso é a bobina.

O QR Code é gerado localmente com `segno` (Python puro) a partir do conteúdo de
`infNFeSupl/qrCode`, que é o que a SEFAZ devolve no XML autorizado. Se o XML não
trouxer `qrCode`, o cupom imprime o aviso em vez de inventar URL — URL de QR
errada leva o consumidor a consulta inválida.

[A VALIDAR] A composição do QR (versão, chave + CSC + hash) é feita pela SEFAZ;
este código só reproduz o que veio no XML. Quem gera o QR é o emissor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from notasbr.xml_util import local, parse_seguro, texto

LARGURA_BOBINA = 80 * mm
MARGEM = 4 * mm
ESCURO = colors.HexColor("#111111")
CINZA = colors.HexColor("#888888")


@dataclass(slots=True)
class ItemCupom:
    descricao: str = ""
    quantidade: str = ""
    unidade: str = ""
    valor_unitario: str = ""
    valor_total: str = ""


@dataclass(slots=True)
class DadosCupom:
    numero: str = ""
    serie: str = ""
    chave: str = ""
    emissao: str = ""
    protocolo: str = ""
    ambiente: str = ""
    emitente_nome: str = ""
    emitente_documento: str = ""
    emitente_endereco: str = ""
    consumidor_documento: str = ""
    itens: list[ItemCupom] = field(default_factory=list)
    valor_produtos: str = ""
    valor_desconto: str = ""
    valor_total: str = ""
    forma_pagamento: str = ""
    valor_pago: str = ""
    qr_code: str = ""
    informacoes_adicionais: str = ""
    ausentes: list[str] = field(default_factory=list)


FORMAS_PAGAMENTO = {
    "01": "Dinheiro",
    "02": "Cheque",
    "03": "Cartão de Crédito",
    "04": "Cartão de Débito",
    "05": "Crédito Loja",
    "10": "Vale Alimentação",
    "11": "Vale Refeição",
    "12": "Vale Presente",
    "13": "Vale Combustível",
    "15": "Boleto Bancário",
    "17": "PIX",
    "90": "Sem Pagamento",
    "99": "Outros",
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


def _data(valor: str) -> str:
    achado = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", valor)
    if not achado:
        return valor
    ano, mes, dia, hora, minuto = achado.groups()
    return f"{dia}/{mes}/{ano} {hora}:{minuto}"


def _documento(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor)
    if len(digitos) == 14:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    return valor


def _procurar_qr_code(raiz) -> str:
    """QR Code do suplemento da NFC-e.

    `infNFeSupl` é irmão de `infNFe` dentro de `NFe`, mas há emissores que
    serializam de forma diferente. Em vez de fixar um caminho e falhar em
    silêncio, procura em ordem de preferência e, por último, qualquer `qrCode`.
    """
    direto = _procurar(raiz, "NFe/infNFeSupl/qrCode", "infNFeSupl/qrCode")
    if direto:
        return direto
    for elemento in raiz.iter():
        if local(elemento.tag) == "qrCode":
            valor = texto(elemento)
            if valor:
                return valor
    return ""


def extrair_cupom(xml: bytes | str) -> DadosCupom:
    """Extrai os campos do cupom a partir do XML autorizado da NFC-e."""
    dados = xml.encode("utf-8") if isinstance(xml, str) else xml
    raiz = parse_seguro(dados)

    chave = ""
    for elemento in raiz.iter():
        if local(elemento.tag) == "infNFe":
            identificador = elemento.get("Id") or ""
            chave = identificador[3:] if identificador.startswith("NFe") else identificador
            break

    tpag = _procurar(raiz, "NFe/infNFe/pag/detPag/tPag")
    cupom = DadosCupom(
        numero=_procurar(raiz, "NFe/infNFe/ide/nNF"),
        serie=_procurar(raiz, "NFe/infNFe/ide/serie"),
        chave=chave,
        emissao=_data(_procurar(raiz, "NFe/infNFe/ide/dhEmi")),
        protocolo=_procurar(raiz, "protNFe/infProt/nProt"),
        ambiente=_procurar(raiz, "NFe/infNFe/ide/tpAmb"),
        emitente_nome=_procurar(raiz, "NFe/infNFe/emit/xNome"),
        emitente_documento=_documento(
            _procurar(raiz, "NFe/infNFe/emit/CNPJ") or _procurar(raiz, "NFe/infNFe/emit/CPF")
        ),
        emitente_endereco=_procurar(raiz, "NFe/infNFe/emit/enderEmit/xLgr"),
        consumidor_documento=_documento(
            _procurar(raiz, "NFe/infNFe/dest/CNPJ") or _procurar(raiz, "NFe/infNFe/dest/CPF")
        ),
        valor_produtos=_moeda(_procurar(raiz, "NFe/infNFe/total/ICMSTot/vProd")),
        valor_desconto=_moeda(_procurar(raiz, "NFe/infNFe/total/ICMSTot/vDesc")),
        valor_total=_moeda(_procurar(raiz, "NFe/infNFe/total/ICMSTot/vNF")),
        forma_pagamento=FORMAS_PAGAMENTO.get(tpag, tpag),
        valor_pago=_moeda(_procurar(raiz, "NFe/infNFe/pag/detPag/vPag")),
        qr_code=_procurar_qr_code(raiz),
        informacoes_adicionais=_procurar(raiz, "NFe/infNFe/infAdic/infCpl"),
    )

    for det in raiz.iter():
        if local(det.tag) != "det":
            continue
        cupom.itens.append(
            ItemCupom(
                descricao=_procurar(det, "prod/xProd"),
                quantidade=_procurar(det, "prod/qCom"),
                unidade=_procurar(det, "prod/uCom"),
                valor_unitario=_moeda(_procurar(det, "prod/vUnCom")),
                valor_total=_moeda(_procurar(det, "prod/vProd")),
            )
        )

    obrigatorios = {
        "chave": cupom.chave,
        "numero": cupom.numero,
        "emitente_nome": cupom.emitente_nome,
        "valor_total": cupom.valor_total,
    }
    cupom.ausentes = [campo for campo, valor in obrigatorios.items() if not valor]
    return cupom


def _qr_para_imagem(conteudo: str) -> ImageReader | None:
    """QR Code em PNG na memória, ou None se não houver conteúdo."""
    if not conteudo:
        return None
    try:
        import segno
    except ImportError:  # pragma: no cover - dependência declarada no pyproject
        return None
    buffer = BytesIO()
    segno.make(conteudo, error="m").save(buffer, kind="png", scale=3, border=1)
    buffer.seek(0)
    return ImageReader(buffer)


def gerar_cupom(dados: DadosCupom) -> bytes:
    """Gera o cupom em PDF, largura de bobina de 80 mm."""
    largura = LARGURA_BOBINA
    linhas_estimadas = 40 + 4 * len(dados.itens)
    altura = max(120 * mm, linhas_estimadas * 3.6 * mm)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(largura, altura))
    pdf.setTitle(f"NFC-e {dados.numero}")
    y = altura - MARGEM

    def centralizado(texto_: str, tamanho: float = 7, negrito: bool = False) -> None:
        nonlocal y
        pdf.setFont("Helvetica-Bold" if negrito else "Helvetica", tamanho)
        pdf.setFillColor(ESCURO)
        pdf.drawCentredString(largura / 2, y, texto_[:70])
        y -= tamanho * 0.55 * mm

    def linha(texto_: str, tamanho: float = 6.6) -> None:
        nonlocal y
        pdf.setFont("Helvetica", tamanho)
        pdf.setFillColor(ESCURO)
        pdf.drawString(MARGEM, y, texto_[:92])
        y -= tamanho * 0.55 * mm

    def par(esquerda: str, direita: str, tamanho: float = 6.6) -> None:
        nonlocal y
        pdf.setFont("Helvetica", tamanho)
        pdf.setFillColor(ESCURO)
        pdf.drawString(MARGEM, y, esquerda[:52])
        pdf.drawRightString(largura - MARGEM, y, direita[:18])
        y -= tamanho * 0.55 * mm

    def separador() -> None:
        nonlocal y
        pdf.setStrokeColor(CINZA)
        pdf.setDash(1, 1)
        pdf.line(MARGEM, y + 1 * mm, largura - MARGEM, y + 1 * mm)
        pdf.setDash()
        y -= 3 * mm

    centralizado("DANFE NFC-e", 9, negrito=True)
    centralizado("Documento Auxiliar da Nota Fiscal de Consumidor Eletrônica", 5.6)
    y -= 2 * mm

    centralizado(dados.emitente_nome or "—", 8, negrito=True)
    centralizado(f"CNPJ {dados.emitente_documento}", 6)
    if dados.emitente_endereco:
        centralizado(dados.emitente_endereco, 5.6)
    separador()

    for item in dados.itens:
        linha(item.descricao, 6.8)
        par(
            f"  {item.quantidade} {item.unidade} x {item.valor_unitario}",
            item.valor_total,
            6.4,
        )
    separador()

    par("VALOR PRODUTOS", dados.valor_produtos or "—")
    if dados.valor_desconto and dados.valor_desconto not in ("0,00", ""):
        par("DESCONTO", dados.valor_desconto)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColor(ESCURO)
    pdf.drawString(MARGEM, y, "TOTAL")
    pdf.drawRightString(largura - MARGEM, y, f"R$ {dados.valor_total}")
    y -= 6 * mm

    if dados.forma_pagamento:
        par(f"PAGAMENTO ({dados.forma_pagamento})", dados.valor_pago or dados.valor_total)
    separador()

    qr = _qr_para_imagem(dados.qr_code)
    if qr is not None:
        tamanho_qr = 26 * mm
        pdf.drawImage(
            qr,
            (largura - tamanho_qr) / 2,
            y - tamanho_qr,
            width=tamanho_qr,
            height=tamanho_qr,
            mask="auto",
        )
        y -= tamanho_qr + 3 * mm
    else:
        centralizado("QR Code não presente no XML autorizado", 6, negrito=True)
        centralizado("consulte pelo endereço da SEFAZ e pela chave abaixo", 5.6)
        y -= 1 * mm

    par("NFC-e número", dados.numero or "—")
    par("Série", dados.serie or "—")
    par("Emissão", dados.emissao or "—")
    if dados.consumidor_documento:
        par("Consumidor", dados.consumidor_documento)
    y -= 1 * mm

    centralizado("CHAVE DE ACESSO", 5.6)
    # Chave em blocos de 4 para leitura por digitação.
    for inicio in range(0, len(dados.chave), 24):
        centralizado(dados.chave[inicio : inicio + 24], 5.8)
    if dados.protocolo:
        par("Protocolo", dados.protocolo)
    y -= 1 * mm

    if dados.informacoes_adicionais:
        separador()
        linha(dados.informacoes_adicionais, 5.6)

    y -= 2 * mm
    centralizado("Tributos aproximados conforme Lei 12.741/2012: vide XML autorizado", 5)
    centralizado("open_notas_br — o XML autorizado prevalece sobre este cupom", 5)
    if dados.ausentes:
        centralizado(f"Campos ausentes no XML: {', '.join(dados.ausentes)}", 4.6)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
