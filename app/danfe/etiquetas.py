"""Etiquetas de identificação de volume, a partir do XML da NF-e autorizada.

Layout pedido nas imagens de referência: cada etiqueta traz

    Volume i/n | Peso (kg) | Nota fiscal | Coleta
    código de barras + código impresso
    DESTINATÁRIO (nome, endereço, CEP)
    REMETENTE   (nome, endereço, CEP)

Decisões que o código torna explícitas:

- **O volume é a unidade, não a nota.** Uma NF-e com 3 volumes gera 3 etiquetas,
  cada uma com a chave da mesma nota e o índice do volume. Sem o índice, o
  conferente não sabe se falta caixa.
- **A quantidade de etiquetas vem do parâmetro**, não só do XML: `transp/vol` é
  opcional e muitos emissores não o preenchem. Se o XML não traz volume e o
  chamador informa N, imprimimos N com peso em branco — nunca inventamos peso.
- **"Coleta" não existe na NF-e.** O campo imprime a data de emissão/saída como
  referência, e isso está marcado aqui e no rodapé do PDF. [A VALIDAR] se o
  cliente usa outro critério (ex.: data do romaneio).

Layout exato (medidas, fontes, posição do código) é **[A VALIDAR]** contra o
manual do parceiro logístico; os campos e a ordem seguem as imagens fornecidas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO

from reportlab.graphics.barcode import code128
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from notasbr.xml_util import local, parse_seguro, texto

LARGURA, ALTURA = A4
MARGEM = 10 * mm
ESCURO = colors.HexColor("#111111")
CINZA = colors.HexColor("#eeeeee")
LINHA = colors.HexColor("#777777")
ALTURA_ETIQUETA = 88 * mm
LARGURA_UTIL = LARGURA - 2 * MARGEM


@dataclass(slots=True)
class Volume:
    """Um volume físico a etiquetar."""

    indice: int
    total: int
    quantidade: str = ""
    especie: str = ""
    peso_liquido: str = ""
    peso_bruto: str = ""
    marca: str = ""


@dataclass(slots=True)
class DadosEtiqueta:
    """Tudo o que a etiqueta imprime, extraído do XML autorizado."""

    numero_nota: str = ""
    serie: str = ""
    chave: str = ""
    coleta: str = ""
    emitente_nome: str = ""
    emitente_endereco: str = ""
    emitente_cep: str = ""
    destinatario_nome: str = ""
    destinatario_endereco: str = ""
    destinatario_cep: str = ""
    volumes: list[Volume] = field(default_factory=list)
    ausentes: list[str] = field(default_factory=list)


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


def _formatar_cep(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor)
    if len(digitos) == 8:
        return f"{digitos[:5]}-{digitos[5:]}"
    return valor


def _formatar_endereco(raiz, prefixo: str) -> str:
    partes = []
    for campo in ("xLgr", "nro", "xCpl", "xBairro", "xMun"):
        valor = _procurar(raiz, f"{prefixo}/{campo}")
        if valor:
            partes.append(valor)
    uf = _procurar(raiz, f"{prefixo}/UF")
    if uf:
        partes.append(uf)
    return ", ".join(partes)


def _formatar_data_hora(valor: str) -> str:
    achado = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", valor)
    if not achado:
        return valor
    ano, mes, dia, hora, minuto = achado.groups()
    return f"{dia}/{mes}/{ano} {hora}:{minuto}"


def _formatar_peso(valor: str) -> str:
    if not valor:
        return ""
    try:
        return f"{Decimal(valor):.3f}".replace(".", ",")
    except (InvalidOperation, ValueError):
        return valor


def extrair_etiquetas(xml: bytes | str, *, quantidade_volumes: int | None = None) -> DadosEtiqueta:
    """Extrai os dados da etiqueta do XML autorizado.

    `quantidade_volumes` sobrepõe o que o XML declara, para o caso comum de nota
    sem `transp/vol` preenchido.
    """
    dados = xml.encode("utf-8") if isinstance(xml, str) else xml
    raiz = parse_seguro(dados)

    chave = ""
    for elemento in raiz.iter():
        if local(elemento.tag) == "infNFe":
            identificador = elemento.get("Id") or ""
            chave = identificador[3:] if identificador.startswith("NFe") else identificador
            break

    nota = DadosEtiqueta(
        numero_nota=_procurar(raiz, "NFe/infNFe/ide/nNF"),
        serie=_procurar(raiz, "NFe/infNFe/ide/serie"),
        chave=chave,
        coleta=_formatar_data_hora(
            _procurar(raiz, "NFe/infNFe/ide/dhSaidaEnt") or _procurar(raiz, "NFe/infNFe/ide/dhEmi")
        ),
        emitente_nome=_procurar(raiz, "NFe/infNFe/emit/xNome"),
        emitente_endereco=_formatar_endereco(raiz, "NFe/infNFe/emit/enderEmit"),
        emitente_cep=_formatar_cep(_procurar(raiz, "NFe/infNFe/emit/enderEmit/CEP")),
        destinatario_nome=_procurar(raiz, "NFe/infNFe/dest/xNome"),
        destinatario_endereco=_formatar_endereco(raiz, "NFe/infNFe/dest/enderDest"),
        destinatario_cep=_formatar_cep(_procurar(raiz, "NFe/infNFe/dest/enderDest/CEP")),
    )

    # `transp/vol/qVol` é a QUANTIDADE de volumes do grupo, não um volume.
    # Um `vol` com qVol=2 significa duas caixas e precisa de duas etiquetas — tratar
    # cada grupo como um volume produziria metade das etiquetas necessárias.
    # O peso no leiaute é o total do grupo; ele é impresso como peso da nota, e a
    # etiqueta diz isso, em vez de dividir por qVol e inventar peso por caixa.
    for elemento in raiz.iter():
        if local(elemento.tag) != "vol":
            continue
        declarado = _procurar(elemento, "qVol")
        try:
            quantidade_de_volumes = max(1, int(declarado or "1"))
        except ValueError:
            # `qVol` ilegível não pode virar 1 etiqueta em silêncio: imprimir menos
            # etiquetas que caixas faz o volume viajar sem identificação. Registra a
            # ausência para o operador passar `quantidade_volumes` explicitamente.
            quantidade_de_volumes = 1
            nota.ausentes.append(f"transp/vol/qVol ilegível ({declarado!r}): 1 etiqueta por grupo")
        for _ in range(quantidade_de_volumes):
            nota.volumes.append(
                Volume(
                    indice=len(nota.volumes) + 1,
                    total=0,
                    quantidade=_procurar(elemento, "qVol"),
                    especie=_procurar(elemento, "esp"),
                    peso_liquido=_formatar_peso(_procurar(elemento, "pesoL")),
                    peso_bruto=_formatar_peso(_procurar(elemento, "pesoB")),
                    marca=_procurar(elemento, "marca"),
                )
            )

    total = quantidade_volumes or len(nota.volumes) or 1
    if not nota.volumes:
        # Nota sem `transp/vol`: imprime a quantidade informada, sem peso.
        nota.volumes = [Volume(indice=i, total=total) for i in range(1, total + 1)]
    else:
        # A quantidade informada manda: se pediram mais etiquetas do que o XML
        # declara, as extras saem sem peso em vez de repetir o peso do primeiro.
        while len(nota.volumes) < total:
            nota.volumes.append(Volume(indice=len(nota.volumes) + 1, total=total))
        nota.volumes = nota.volumes[:total]
    for volume in nota.volumes:
        volume.total = total

    obrigatorios = {
        "numero_nota": nota.numero_nota,
        "chave": nota.chave,
        "emitente_nome": nota.emitente_nome,
        "destinatario_nome": nota.destinatario_nome,
    }
    # Preserva o que a extração já registrou (ex.: `qVol` ilegível): sobrescrever aqui
    # apagaria o aviso de contagem de etiquetas.
    nota.ausentes = nota.ausentes + [campo for campo, valor in obrigatorios.items() if not valor]
    return nota


def _prefixo_codigo(nome: str) -> str:
    """Prefixo do código impresso, como nas etiquetas de referência (`BLING...`)."""
    limpo = re.sub(r"[^A-Za-z]", "", nome).upper()
    return (limpo[:5] or "NFE").ljust(5, "X")


def codigo_do_volume(dados: DadosEtiqueta, volume: Volume) -> str:
    """Código impresso e codificado na barra: `<prefixo><nota>V<volume>`.

    Ex.: `PETRO0000018V1` — nota 18, volume 1. Determinístico, para que a
    reimpressão produza o mesmo código.
    """
    prefixo = _prefixo_codigo(dados.emitente_nome)
    numero = re.sub(r"\D", "", dados.numero_nota).rjust(7, "0")
    return f"{prefixo}{numero}V{volume.indice}"


def _desenhar_etiqueta(
    pdf: canvas.Canvas, dados: DadosEtiqueta, volume: Volume, topo: float
) -> None:
    base = topo - ALTURA_ETIQUETA
    pdf.setStrokeColor(LINHA)
    pdf.rect(MARGEM, base, LARGURA_UTIL, ALTURA_ETIQUETA, fill=0, stroke=1)
    y = topo - 7 * mm

    # Cabeçalho: Volume i/n
    pdf.setFont("Helvetica-Bold", 13)
    pdf.setFillColor(ESCURO)
    pdf.drawString(MARGEM + 4 * mm, y, f"Volume {volume.indice}/{volume.total}")
    if volume.especie:
        pdf.setFont("Helvetica", 9)
        pdf.drawRightString(LARGURA - MARGEM - 4 * mm, y, volume.especie)
    y -= 5 * mm

    # Faixa de campos
    pdf.setFillColor(CINZA)
    pdf.rect(MARGEM + 2 * mm, y - 9 * mm, LARGURA_UTIL - 4 * mm, 10 * mm, fill=1, stroke=0)
    pdf.setFillColor(ESCURO)
    campos = [
        ("PESO (kg)", volume.peso_bruto or volume.peso_liquido or "—"),
        ("NOTA FISCAL", dados.numero_nota or "—"),
        ("SÉRIE", dados.serie or "—"),
        ("COLETA", dados.coleta or "—"),
    ]
    largura_campo = (LARGURA_UTIL - 8 * mm) / len(campos)
    for posicao, (rotulo, valor) in enumerate(campos):
        x = MARGEM + 4 * mm + posicao * largura_campo
        pdf.setFont("Helvetica", 6.2)
        pdf.setFillColor(colors.HexColor("#555555"))
        pdf.drawString(x, y - 2.5 * mm, rotulo)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.setFillColor(ESCURO)
        pdf.drawString(x, y - 6.5 * mm, valor[:22])
    y -= 14 * mm

    # Código de barras
    codigo = codigo_do_volume(dados, volume)
    barra = code128.Code128(codigo, barHeight=11 * mm, barWidth=0.62)
    barra.drawOn(pdf, MARGEM + 4 * mm, y - 11 * mm)
    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(ESCURO)
    pdf.drawString(MARGEM + 4 * mm, y - 14.5 * mm, codigo)
    y -= 20 * mm

    # Destinatário
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.setFillColor(colors.HexColor("#444444"))
    pdf.drawString(MARGEM + 4 * mm, y, "DESTINATÁRIO")
    y -= 4.5 * mm
    pdf.setFillColor(ESCURO)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(MARGEM + 4 * mm, y, (dados.destinatario_nome or "—")[:60])
    y -= 4.5 * mm
    pdf.setFont("Helvetica", 8)
    for parte in _quebrar(dados.destinatario_endereco, 78):
        pdf.drawString(MARGEM + 4 * mm, y, parte)
        y -= 3.6 * mm
    if dados.destinatario_cep:
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(MARGEM + 4 * mm, y, f"CEP {dados.destinatario_cep}")
        y -= 3.6 * mm

    y -= 2 * mm
    pdf.setStrokeColor(LINHA)
    pdf.line(MARGEM + 3 * mm, y + 1.5 * mm, LARGURA - MARGEM - 3 * mm, y + 1.5 * mm)
    y -= 3 * mm

    # Remetente
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.setFillColor(colors.HexColor("#444444"))
    pdf.drawString(MARGEM + 4 * mm, y, "REMETENTE")
    y -= 4.5 * mm
    pdf.setFillColor(ESCURO)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(MARGEM + 4 * mm, y, (dados.emitente_nome or "—")[:60])
    y -= 4 * mm
    pdf.setFont("Helvetica", 7.6)
    pdf.drawString(MARGEM + 4 * mm, y, dados.emitente_endereco[:96])
    if dados.emitente_cep:
        y -= 3.6 * mm
        pdf.setFont("Helvetica-Bold", 8.4)
        pdf.drawString(MARGEM + 4 * mm, y, f"CEP {dados.emitente_cep}")

    # Chave da nota no rodapé da etiqueta, para conferência por leitor
    pdf.setFont("Helvetica", 6.4)
    pdf.setFillColor(colors.HexColor("#666666"))
    pdf.drawString(MARGEM + 4 * mm, base + 5 * mm, f"Chave da NF-e: {dados.chave}")
    pdf.drawString(
        MARGEM + 4 * mm,
        base + 2 * mm,
        "Coleta = data de saída/emissão da NF-e. Peso = total do grupo de volumes "
        "no XML, não o peso desta caixa.",
    )


def _quebrar(texto_: str, largura: int) -> list[str]:
    linhas: list[str] = []
    atual = ""
    for palavra in (texto_ or "").split():
        if len(atual) + len(palavra) + 1 > largura:
            if atual:
                linhas.append(atual)
            atual = palavra
        else:
            atual = f"{atual} {palavra}".strip()
    if atual:
        linhas.append(atual)
    return linhas or ["—"]


def gerar_etiquetas(dados: DadosEtiqueta) -> bytes:
    """Gera o PDF com uma etiqueta por volume."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(f"Etiquetas NF-e {dados.numero_nota}")

    por_pagina = 2  # duas etiquetas por folha A4
    topo = ALTURA - MARGEM
    for indice, volume in enumerate(dados.volumes):
        if indice > 0 and indice % por_pagina == 0:
            pdf.showPage()
            topo = ALTURA - MARGEM
        _desenhar_etiqueta(pdf, dados, volume, topo)
        topo -= ALTURA_ETIQUETA + 4 * mm

    if dados.ausentes:
        pdf.setFont("Helvetica", 6)
        pdf.setFillColor(colors.HexColor("#aa0000"))
        pdf.drawString(
            MARGEM,
            MARGEM,
            f"Campos não encontrados no XML: {', '.join(dados.ausentes)}",
        )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
