"""Geração local do DANFSe em PDF.

Por que **ReportLab** e não WeasyPrint: o serviço precisa gerar PDF no container
Linux *e* na máquina do desenvolvedor (Windows). WeasyPrint depende de pango/cairo
nativos, que no Windows são uma fonte recorrente de "não roda aqui"; ReportLab é
Python puro e produz o mesmo resultado nos dois. O DANFSe é formulário de posições
fixas — o modelo de canvas do ReportLab encaixa melhor que HTML/CSS.

Regras do produto:

- **Toda informação vem do XML.** Nenhum campo é recalculado aqui; se o XML não
  tem o dado, o PDF mostra vazio e o rodapé lista o que faltou.
- **O XML prevalece sobre o PDF.** Se divergirem, vale o autorizado.
- Nota sem IBS/CBS imprime o bloco com "não sujeito", em vez de omitir a seção —
  a NT 008 v2 prevê a seção, e seção ausente é ambígua para quem confere.
"""

from __future__ import annotations

from io import BytesIO

from reportlab.graphics.barcode import code128
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.danfse.model import DanfseData

LARGURA, ALTURA = A4
MARGEM = 12 * mm
CINZA = colors.HexColor("#e8e8e8")
ESCURO = colors.HexColor("#222222")
LINHA = colors.HexColor("#999999")


class _Desenhista:
    """Acumula o desenho do PDF com controle de posição vertical."""

    def __init__(self, canvas_pdf: canvas.Canvas) -> None:
        self.pdf = canvas_pdf
        self.y = ALTURA - MARGEM

    def titulo(self, texto: str) -> None:
        self.pdf.setFont("Helvetica-Bold", 9)
        self.pdf.setFillColor(ESCURO)
        self.pdf.setStrokeColor(LINHA)
        self.pdf.setFillColor(CINZA)
        self.pdf.rect(MARGEM, self.y - 4.6 * mm, LARGURA - 2 * MARGEM, 5.2 * mm, fill=1, stroke=0)
        self.pdf.setFillColor(ESCURO)
        self.pdf.drawString(MARGEM + 2 * mm, self.y - 3.4 * mm, texto)
        self.y -= 6.6 * mm

    def linha(self, rotulo: str, valor: str, largura_valor: float | None = None) -> None:
        if not valor:
            return
        self.pdf.setFont("Helvetica", 6.6)
        self.pdf.setFillColor(colors.HexColor("#555555"))
        self.pdf.drawString(MARGEM + 1 * mm, self.y, rotulo)
        self.pdf.setFont("Helvetica-Bold", 7.4)
        self.pdf.setFillColor(ESCURO)
        self.pdf.drawString(MARGEM + 34 * mm, self.y, valor[:110])
        self.y -= 3.5 * mm

    def par(self, esquerda: tuple[str, str], direita: tuple[str, str]) -> None:
        """Duas colunas na mesma linha."""
        if not esquerda[1] and not direita[1]:
            return
        self.pdf.setFont("Helvetica", 6.6)
        self.pdf.setFillColor(colors.HexColor("#555555"))
        self.pdf.drawString(MARGEM + 1 * mm, self.y, esquerda[0])
        self.pdf.drawString(MARGEM + 96 * mm, self.y, direita[0])
        self.pdf.setFont("Helvetica-Bold", 7.4)
        self.pdf.setFillColor(ESCURO)
        self.pdf.drawString(MARGEM + 34 * mm, self.y, esquerda[1][:60])
        self.pdf.drawString(MARGEM + 122 * mm, self.y, direita[1][:60])
        self.y -= 3.5 * mm

    def texto_longo(self, rotulo: str, valor: str) -> None:
        if not valor:
            return
        self.pdf.setFont("Helvetica", 6.6)
        self.pdf.setFillColor(colors.HexColor("#555555"))
        self.pdf.drawString(MARGEM + 1 * mm, self.y, rotulo)
        self.y -= 3.2 * mm
        self.pdf.setFont("Helvetica-Bold", 7.2)
        self.pdf.setFillColor(ESCURO)
        for parte in _quebrar(valor, 120):
            self.pdf.drawString(MARGEM + 1 * mm, self.y, parte)
            self.y -= 3.2 * mm

    def espaco(self, pontos: float = 2.0) -> None:
        self.y -= pontos * mm


def _quebrar(texto: str, largura: int) -> list[str]:
    """Quebra texto em linhas de até `largura` caracteres, sem cortar palavra."""
    linhas: list[str] = []
    atual = ""
    for palavra in texto.split():
        if len(atual) + len(palavra) + 1 > largura:
            if atual:
                linhas.append(atual)
            atual = palavra
        else:
            atual = f"{atual} {palavra}".strip()
    if atual:
        linhas.append(atual)
    return linhas or [""]


def _cabecalho(desenho: _Desenhista, dados: DanfseData) -> None:
    pdf = desenho.pdf
    pdf.setFont("Helvetica-Bold", 11)
    pdf.setFillColor(ESCURO)
    pdf.drawString(MARGEM, desenho.y, "DANFSe v2.0")
    pdf.setFont("Helvetica", 7)
    pdf.drawString(
        MARGEM,
        desenho.y - 4 * mm,
        "Documento Auxiliar da NFS-e — representação do XML autorizado (NT 008/2026)",
    )
    pdf.setFont("Helvetica", 6.4)
    pdf.setFillColor(colors.HexColor("#555555"))
    pdf.drawRightString(LARGURA - MARGEM, desenho.y, f"Layout {dados.versao_layout or 'n/d'}")
    desenho.y -= 9 * mm

    pdf.setFont("Helvetica", 6.6)
    pdf.setFillColor(colors.HexColor("#555555"))
    pdf.drawString(MARGEM, desenho.y, "CHAVE DE ACESSO")
    desenho.y -= 4.5 * mm
    if dados.chave_acesso:
        codigo = code128.Code128(dados.chave_acesso, barHeight=11 * mm, barWidth=0.28)
        codigo.drawOn(pdf, MARGEM, desenho.y - 11 * mm)
        pdf.setFont("Helvetica", 7)
        pdf.setFillColor(ESCURO)
        pdf.drawString(MARGEM, desenho.y - 14.5 * mm, _formatar_chave(dados.chave_acesso))
        desenho.y -= 18 * mm


def _formatar_chave(chave: str) -> str:
    """Agrupa a chave em blocos de 4 para leitura humana."""
    return " ".join(chave[i : i + 4] for i in range(0, len(chave), 4))


def gerar_danfse(dados: DanfseData) -> bytes:
    """Gera o PDF do DANFSe e devolve os bytes."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(f"DANFSe {dados.chave_acesso or dados.numero}")
    pdf.setAuthor(dados.prestador.nome or "open_notas_br")
    pdf.setSubject("DANFSe v2.0")

    desenho = _Desenhista(pdf)
    _cabecalho(desenho, dados)

    # --- Identificação -------------------------------------------------
    desenho.titulo("IDENTIFICAÇÃO DA NFS-e")
    desenho.par(("Número", dados.numero), ("Competência", dados.competencia))
    desenho.par(
        ("Emissão da DPS", dados.data_emissao_dps), ("Processamento", dados.data_processamento)
    )
    desenho.par(("Série da DPS", dados.serie_dps), ("Número da DPS", dados.numero_dps))
    desenho.par(("Emitente", dados.emitente), ("Situação", dados.situacao))
    desenho.par(("Finalidade", dados.finalidade), ("Ambiente", dados.ambiente))
    desenho.espaco()

    # --- Prestador -----------------------------------------------------
    desenho.titulo("PRESTADOR DE SERVIÇOS")
    desenho.par(
        ("CNPJ/CPF", dados.prestador.documento),
        ("Inscrição municipal", dados.prestador.inscricao_municipal),
    )
    desenho.linha("Nome / Razão social", dados.prestador.nome)
    desenho.par(("Telefone", dados.prestador.telefone), ("E-mail", dados.prestador.email))
    desenho.linha("Endereço", dados.prestador.endereco)
    desenho.par(
        ("Simples Nacional", dados.prestador.opcao_simples),
        ("Regime", dados.prestador.regime_simples),
    )
    desenho.espaco()

    # --- Tomador --------------------------------------------------------
    desenho.titulo("TOMADOR DE SERVIÇOS")
    if dados.tomador is None:
        desenho.linha("Tomador", "NÃO IDENTIFICADO NA NFS-e")
    else:
        desenho.par(
            ("CNPJ/CPF", dados.tomador.documento),
            ("Inscrição municipal", dados.tomador.inscricao_municipal),
        )
        desenho.linha("Nome / Razão social", dados.tomador.nome)
        desenho.linha("Endereço", dados.tomador.endereco)
        desenho.par(("Telefone", dados.tomador.telefone), ("E-mail", dados.tomador.email))
    desenho.espaco()

    # --- Serviço --------------------------------------------------------
    desenho.titulo("SERVIÇO PRESTADO")
    desenho.par(("Código de tributação", dados.codigo_tributacao), ("Código NBS", dados.codigo_nbs))
    desenho.linha("Local da prestação", dados.local_prestacao)
    desenho.texto_longo("Descrição do serviço", dados.descricao_servico)
    desenho.espaco()

    # --- ISSQN ----------------------------------------------------------
    desenho.titulo("TRIBUTAÇÃO MUNICIPAL (ISSQN)")
    if dados.issqn.nao_sujeito:
        desenho.linha("ISSQN", "NÃO SUJEITO — operação sem incidência de ISSQN")
    else:
        desenho.par(
            ("Tributação do ISSQN", dados.issqn.trib_issqn), ("Retenção", dados.issqn.retencao)
        )
        desenho.par(
            ("Alíquota", dados.issqn.aliquota), ("Base de cálculo", dados.issqn.base_calculo)
        )
        desenho.par(
            ("Regime especial", dados.issqn.regime_especial),
            ("Benefício municipal", dados.issqn.beneficio_municipal),
        )
    desenho.espaco()

    # --- Federal --------------------------------------------------------
    desenho.titulo("TRIBUTAÇÃO FEDERAL (exceto CBS)")
    desenho.par(
        ("IRRF", dados.federal.ret_irrf), ("Contribuição previdenciária", dados.federal.ret_cp)
    )
    desenho.par(
        ("CSLL", dados.federal.ret_csll), ("Retenção PIS/COFINS", dados.federal.ret_pis_cofins)
    )
    desenho.espaco()

    # --- IBS/CBS --------------------------------------------------------
    desenho.titulo("TRIBUTAÇÃO IBS / CBS")
    if dados.tem_ibscbs():
        desenho.par(
            ("CST / classificação", dados.ibscbs.cst_class),
            ("Base de cálculo", dados.ibscbs.base_calculo),
        )
        desenho.par(
            ("Alíquota IBS UF", dados.ibscbs.aliquota_ibs_uf),
            ("Alíquota IBS Município", dados.ibscbs.aliquota_ibs_mun),
        )
        desenho.par(
            ("Valor IBS UF", dados.ibscbs.valor_ibs_uf),
            ("Valor IBS Município", dados.ibscbs.valor_ibs_mun),
        )
        desenho.par(
            ("Total IBS", dados.ibscbs.total_ibs), ("Alíquota CBS", dados.ibscbs.aliquota_cbs)
        )
        desenho.par(
            ("Valor CBS", dados.ibscbs.valor_cbs), ("Total IBS + CBS", dados.ibscbs.total_ibs_cbs)
        )
    else:
        desenho.linha(
            "IBS/CBS",
            "NÃO INFORMADO NA NFS-e — nota sem grupo IBSCBS (competência anterior ou regime não sujeito)",
        )
    desenho.espaco()

    # --- Totais ---------------------------------------------------------
    desenho.titulo("VALOR TOTAL DA NFS-e")
    desenho.par(
        ("Valor do serviço", dados.totais.valor_servico),
        ("Desconto incondicionado", dados.totais.desconto_incondicionado),
    )
    desenho.par(
        ("Desconto condicionado", dados.totais.desconto_condicionado),
        ("Retenções", dados.totais.total_retencoes),
    )
    desenho.par(
        ("Valor líquido", dados.totais.valor_liquido),
        ("Total IBS + CBS", dados.totais.total_ibs_cbs),
    )
    desenho.linha("Líquido + IBS/CBS", dados.totais.valor_liquido_mais_ibs_cbs)

    # --- Rodapé ---------------------------------------------------------
    pdf.setFont("Helvetica", 5.8)
    pdf.setFillColor(colors.HexColor("#666666"))
    rodape_y = MARGEM + 10 * mm
    pdf.drawString(
        MARGEM,
        rodape_y,
        "O XML autorizado prevalece sobre este documento. Gerado localmente por open_notas_br.",
    )
    pdf.drawString(
        MARGEM,
        rodape_y - 3 * mm,
        "DANFSe v2 conforme NT 008/2026 (layout declarado pela implementação de referência: v1.01, 30/06/2026).",
    )
    if dados.ausentes:
        pdf.drawString(
            MARGEM,
            rodape_y - 6 * mm,
            f"Campos não encontrados no XML: {', '.join(dados.ausentes[:8])}"
            + ("…" if len(dados.ausentes) > 8 else ""),
        )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
