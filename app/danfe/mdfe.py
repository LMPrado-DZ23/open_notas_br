"""DAMDFE — representação impressa do MDF-e, a partir do XML autorizado.

Blocos:

1. Emitente (transportadora): nome, CNPJ, IE, endereço
2. Identificação: número, série, modelo, emissão, ambiente
3. Percurso: UF de início, UF de fim, municípios de carregamento e descarga
4. Modal rodoviário: placa, tara, capacidade (kg e m³)
5. Documentos vinculados: chaves dos CT-e
6. Totais: quantidade de CT-e/NF-e, valor da carga, peso
7. Chave de acesso + protocolo

**Grau de confiança do leiaute: [A VALIDAR], e mais forte que nos outros
documentos.** NF-e (4.00) e CT-e (4.00) têm XSD na base de referência local;
**MDF-e não tem**. Este mapeamento vem de conhecimento geral do leiaute 3.00
(ide/emit/infModal/infDoc/tot) e precisa ser conferido contra o XSD e o MOC
oficiais antes de uso em produção.

O que o código garante independentemente do leiaute: todo campo sai do XML, e o
que faltar é impresso como ausente em vez de suposto.
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
class DadosDamdfe:
    chave: str = ""
    protocolo: str = ""
    numero: str = ""
    serie: str = ""
    modelo: str = ""
    emissao: str = ""
    ambiente: str = ""
    tipo_transporte: str = ""
    modal: str = ""

    emitente_nome: str = ""
    emitente_documento: str = ""
    emitente_ie: str = ""
    emitente_endereco: str = ""
    emitente_municipio_uf: str = ""

    uf_inicio: str = ""
    uf_fim: str = ""
    municipios_carregamento: list[str] = field(default_factory=list)
    municipios_descarga: list[str] = field(default_factory=list)
    ufs_percurso: list[str] = field(default_factory=list)

    placa: str = ""
    tara: str = ""
    capacidade_kg: str = ""
    capacidade_m3: str = ""

    chaves_cte: list[str] = field(default_factory=list)
    quantidade_cte: str = ""
    quantidade_nfe: str = ""
    valor_carga: str = ""
    unidade_carga: str = ""
    quantidade_carga: str = ""

    informacoes_adicionais: str = ""
    ausentes: list[str] = field(default_factory=list)


MODAIS = {
    "1": "1-Rodoviário",
    "2": "2-Aéreo",
    "3": "3-Aquaviário",
    "4": "4-Ferroviário",
}

UNIDADES_CARGA = {"01": "KG", "02": "TON"}


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


def extrair_damdfe(xml: bytes | str) -> DadosDamdfe:
    """Extrai os campos do DAMDFE do XML autorizado do MDF-e."""
    dados = xml.encode("utf-8") if isinstance(xml, str) else xml
    raiz = parse_seguro(dados)

    chave = ""
    for elemento in raiz.iter():
        if local(elemento.tag) == "infMDFe":
            identificador = elemento.get("Id") or ""
            chave = identificador[4:] if identificador.startswith("MDFe") else identificador
            break

    modal = _procurar(raiz, "MDFe/infMDFe/ide/modTransp")
    unidade = _procurar(raiz, "MDFe/infMDFe/tot/cUnid")

    dados_mdfe = DadosDamdfe(
        chave=chave,
        protocolo=_procurar(raiz, "protMDFe/infProt/nProt"),
        numero=_procurar(raiz, "MDFe/infMDFe/ide/nMDF"),
        serie=_procurar(raiz, "MDFe/infMDFe/ide/serie"),
        modelo=_procurar(raiz, "MDFe/infMDFe/ide/mod"),
        emissao=_data(_procurar(raiz, "MDFe/infMDFe/ide/dhEmi")),
        ambiente=_procurar(raiz, "MDFe/infMDFe/ide/tpAmb"),
        tipo_transporte=_procurar(raiz, "MDFe/infMDFe/ide/tpTransp"),
        modal=MODAIS.get(modal, modal),
        emitente_nome=_procurar(raiz, "MDFe/infMDFe/emit/xNome"),
        emitente_documento=_documento(
            _procurar(raiz, "MDFe/infMDFe/emit/CNPJ") or _procurar(raiz, "MDFe/infMDFe/emit/CPF")
        ),
        emitente_ie=_procurar(raiz, "MDFe/infMDFe/emit/IE"),
        emitente_endereco=", ".join(
            filter(
                None,
                [
                    _procurar(raiz, "MDFe/infMDFe/emit/enderEmit/xLgr"),
                    _procurar(raiz, "MDFe/infMDFe/emit/enderEmit/nro"),
                    _procurar(raiz, "MDFe/infMDFe/emit/enderEmit/xBairro"),
                ],
            )
        ),
        emitente_municipio_uf=" / ".join(
            filter(
                None,
                [
                    _procurar(raiz, "MDFe/infMDFe/emit/enderEmit/xMun"),
                    _procurar(raiz, "MDFe/infMDFe/emit/enderEmit/UF"),
                ],
            )
        ),
        uf_inicio=_procurar(raiz, "MDFe/infMDFe/ide/UFIni"),
        uf_fim=_procurar(raiz, "MDFe/infMDFe/ide/UFFim"),
        placa=_procurar(raiz, "MDFe/infMDFe/infModal/rodo/placa"),
        tara=_procurar(raiz, "MDFe/infMDFe/infModal/rodo/tara"),
        capacidade_kg=_procurar(raiz, "MDFe/infMDFe/infModal/rodo/capKG"),
        capacidade_m3=_procurar(raiz, "MDFe/infMDFe/infModal/rodo/capM3"),
        quantidade_cte=_procurar(raiz, "MDFe/infMDFe/tot/qCTe"),
        quantidade_nfe=_procurar(raiz, "MDFe/infMDFe/tot/qNFe"),
        valor_carga=_moeda(_procurar(raiz, "MDFe/infMDFe/tot/vCarga")),
        unidade_carga=UNIDADES_CARGA.get(unidade, unidade),
        quantidade_carga=_procurar(raiz, "MDFe/infMDFe/tot/qCarga"),
        informacoes_adicionais=_procurar(raiz, "MDFe/infMDFe/infAdic/infCpl"),
    )

    # Municípios de carregamento e descarga, UFs de percurso e chaves de CT-e.
    # A ordem do documento é preservada: é a ordem de conferência da rota.
    for elemento in raiz.iter():
        tag = local(elemento.tag)
        if tag == "infMunCarrega":
            nome = _procurar(elemento, "xMunCarrega")
            if nome:
                dados_mdfe.municipios_carregamento.append(nome)
        elif tag == "infMunDescarga":
            nome = _procurar(elemento, "xMunDescarga")
            if nome:
                dados_mdfe.municipios_descarga.append(nome)
        elif tag == "infPercurso":
            uf = _procurar(elemento, "UFPerc")
            if uf:
                dados_mdfe.ufs_percurso.append(uf)
        elif tag == "infCTe":
            chave_cte = _procurar(elemento, "chCTe")
            if chave_cte:
                dados_mdfe.chaves_cte.append(chave_cte)

    obrigatorios = {
        "chave": dados_mdfe.chave,
        "numero": dados_mdfe.numero,
        "emitente_nome": dados_mdfe.emitente_nome,
        "uf_inicio": dados_mdfe.uf_inicio,
        "valor_carga": dados_mdfe.valor_carga,
        "protocolo": dados_mdfe.protocolo,
    }
    dados_mdfe.ausentes = [campo for campo, valor in obrigatorios.items() if not valor]
    return dados_mdfe


def gerar_damdfe(dados: DadosDamdfe) -> bytes:
    """Gera o DAMDFE em PDF (A4 paisagem)."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
    pdf.setTitle(f"DAMDFE {dados.chave}")

    largura, altura = landscape(A4)
    margem = 8 * mm
    util = largura - 2 * margem
    y = altura - margem

    pdf.setFont("Helvetica-Bold", 12)
    pdf.setFillColor(ESCURO)
    pdf.drawString(margem, y, "DAMDFE")
    pdf.setFont("Helvetica", 6.6)
    pdf.drawString(
        margem,
        y - 4 * mm,
        "Documento Auxiliar do Manifesto Eletrônico de Documentos Fiscais — "
        "o XML autorizado prevalece sobre este impresso",
    )
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawRightString(
        largura - margem, y, f"MDF-e {dados.numero}  Série {dados.serie}  Modelo {dados.modelo}"
    )
    pdf.setFont("Helvetica", 7)
    pdf.drawRightString(largura - margem, y - 4 * mm, f"{dados.modal}   {dados.emissao}")
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
            pdf.drawString(margem + 34 * mm, y, valor[:165])
            y -= 3.5 * mm
        pdf.setStrokeColor(LINHA)
        pdf.rect(
            margem, topo - altura_bloco * mm + 2 * mm, util, altura_bloco * mm, fill=0, stroke=1
        )
        y -= 3 * mm

    bloco(
        "EMITENTE",
        [
            ("NOME/RAZÃO SOCIAL", dados.emitente_nome),
            ("CNPJ/CPF", dados.emitente_documento),
            ("INSCRIÇÃO ESTADUAL", dados.emitente_ie),
            ("ENDEREÇO", dados.emitente_endereco),
            ("MUNICÍPIO/UF", dados.emitente_municipio_uf),
        ],
        26,
    )
    bloco(
        "PERCURSO",
        [
            ("UF DE INÍCIO", dados.uf_inicio),
            ("UF DE FIM", dados.uf_fim),
            ("CARREGAMENTO", ", ".join(dados.municipios_carregamento) or "não informado"),
            ("DESCARGA", ", ".join(dados.municipios_descarga) or "não informado"),
            ("UFs DO PERCURSO", ", ".join(dados.ufs_percurso) or "não informado"),
        ],
        26,
    )
    bloco(
        "MODAL RODOVIÁRIO",
        [
            ("PLACA DO VEÍCULO", dados.placa),
            ("TARA (kg)", dados.tara),
            ("CAPACIDADE (kg)", dados.capacidade_kg),
            ("CAPACIDADE (m³)", dados.capacidade_m3),
            ("TIPO DE TRANSPORTE", dados.tipo_transporte),
        ],
        26,
    )
    bloco(
        "DOCUMENTOS VINCULADOS E TOTAIS",
        [
            ("QUANTIDADE DE CT-e", dados.quantidade_cte),
            ("QUANTIDADE DE NF-e", dados.quantidade_nfe),
            ("VALOR DA CARGA", dados.valor_carga),
            ("PESO DA CARGA", f"{dados.quantidade_carga} {dados.unidade_carga}".strip()),
            ("CHAVES DOS CT-e", ", ".join(dados.chaves_cte) or "nenhuma chave no XML"),
        ],
        26,
    )
    if dados.informacoes_adicionais:
        bloco(
            "INFORMAÇÕES COMPLEMENTARES",
            [("OBSERVAÇÕES", dados.informacoes_adicionais)],
            10,
        )

    pdf.setFont("Helvetica", 5.8)
    pdf.setFillColor(colors.HexColor("#666666"))
    pdf.drawString(
        margem,
        5 * mm,
        "Gerado localmente por open_notas_br. Leiaute MDF-e [A VALIDAR]: não há XSD de "
        "MDF-e na base de referência; conferir contra o MOC antes de produção.",
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
