"""DANFE A4 a partir do XML autorizado da NF-e.

Cobre os blocos que a representação impressa precisa para conferência:

1. Emitente (identificação, endereço, IE)
2. Destinatário/remetente
3. Fatura/duplicatas
4. Cálculo do imposto
5. Transportador e volumes
6. Dados dos produtos/serviços (itens)
7. Dados adicionais

Não implementa: modais específicos (combustível, medicamento, veículos), código
de barras do protocolo em Code128 do padrão oficial, nem as marcas d'água do
manual. O leiaute exato (medidas, posições, fontes) é **[A VALIDAR]** contra o
Manual de Orientação do Contribuinte vigente — o que existe aqui é o conteúdo
completo em layout legível e estável, não uma réplica homologada.

Regra do produto: **todo campo sai do XML**. O que não estiver no XML imprime
vazio e é listado no rodapé, para ninguém supor valor.
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
class ItemNfe:
    codigo: str = ""
    descricao: str = ""
    ncm: str = ""
    cfop: str = ""
    unidade: str = ""
    quantidade: str = ""
    valor_unitario: str = ""
    valor_total: str = ""


@dataclass(slots=True)
class DadosDanfeA4:
    chave: str = ""
    protocolo: str = ""
    numero: str = ""
    serie: str = ""
    modelo: str = ""
    emissao: str = ""
    saida: str = ""
    operacao: str = ""
    natureza: str = ""
    tipo_emissao: str = ""
    ambiente: str = ""

    emitente_nome: str = ""
    emitente_documento: str = ""
    emitente_ie: str = ""
    emitente_endereco: str = ""
    emitente_municipio_uf: str = ""
    emitente_cep: str = ""
    emitente_telefone: str = ""

    destinatario_nome: str = ""
    destinatario_documento: str = ""
    destinatario_ie: str = ""
    destinatario_endereco: str = ""
    destinatario_municipio_uf: str = ""
    destinatario_cep: str = ""
    destinatario_telefone: str = ""

    base_icms: str = ""
    valor_icms: str = ""
    base_icms_st: str = ""
    valor_icms_st: str = ""
    valor_produtos: str = ""
    valor_frete: str = ""
    valor_seguro: str = ""
    valor_desconto: str = ""
    valor_outras: str = ""
    valor_ipi: str = ""
    valor_total: str = ""

    transportador_nome: str = ""
    transportador_documento: str = ""
    transportador_ie: str = ""
    transportador_endereco: str = ""
    transportador_municipio_uf: str = ""
    modalidade_frete: str = ""
    volumes: list[dict[str, str]] = field(default_factory=list)

    informacoes_adicionais: str = ""
    itens: list[ItemNfe] = field(default_factory=list)
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


def _endereco(raiz, prefixo: str) -> tuple[str, str, str]:
    partes = []
    for campo in ("xLgr", "nro", "xCpl", "xBairro"):
        valor = _procurar(raiz, f"{prefixo}/{campo}")
        if valor:
            partes.append(valor)
    municipio = _procurar(raiz, f"{prefixo}/xMun")
    uf = _procurar(raiz, f"{prefixo}/UF")
    municipio_uf = f"{municipio}/{uf}" if municipio or uf else ""
    cep = _procurar(raiz, f"{prefixo}/CEP")
    if len(re.sub(r"\D", "", cep)) == 8:
        digitos = re.sub(r"\D", "", cep)
        cep = f"{digitos[:5]}-{digitos[5:]}"
    return ", ".join(partes), municipio_uf, cep


MODALIDADES_FRETE = {
    "0": "0-Contratação do Frete por conta do Remetente (CIF)",
    "1": "1-Contratação do Frete por conta do Destinatário (FOB)",
    "2": "2-Contratação do Frete por conta de Terceiros",
    "3": "3-Transporte Próprio por conta do Remetente",
    "4": "4-Transporte Próprio por conta do Destinatário",
    "9": "9-Sem Ocorrência de Transporte",
}


def extrair_danfe_a4(xml: bytes | str) -> DadosDanfeA4:
    """Extrai os campos do DANFE A4 do XML autorizado."""
    dados = xml.encode("utf-8") if isinstance(xml, str) else xml
    raiz = parse_seguro(dados)

    chave = ""
    for elemento in raiz.iter():
        if local(elemento.tag) == "infNFe":
            identificador = elemento.get("Id") or ""
            chave = identificador[3:] if identificador.startswith("NFe") else identificador
            break

    emitente_endereco, emitente_municipio_uf, emitente_cep = _endereco(
        raiz, "NFe/infNFe/emit/enderEmit"
    )
    destinatario_endereco, destinatario_municipio_uf, destinatario_cep = _endereco(
        raiz, "NFe/infNFe/dest/enderDest"
    )
    transportador_endereco, transportador_municipio_uf, _ = _endereco(
        raiz, "NFe/infNFe/transp/transporta/enderTransporta"
    )

    modalidade = _procurar(raiz, "NFe/infNFe/transp/modFrete")

    nota = DadosDanfeA4(
        chave=chave,
        protocolo=_procurar(raiz, "protNFe/infProt/nProt"),
        numero=_procurar(raiz, "NFe/infNFe/ide/nNF"),
        serie=_procurar(raiz, "NFe/infNFe/ide/serie"),
        modelo=_procurar(raiz, "NFe/infNFe/ide/mod"),
        emissao=_data(_procurar(raiz, "NFe/infNFe/ide/dhEmi")),
        saida=_data(_procurar(raiz, "NFe/infNFe/ide/dhSaiEnt")),
        operacao="1-SAÍDA"
        if (_procurar(raiz, "NFe/infNFe/ide/tpNF") or "1") == "1"
        else "0-ENTRADA",
        natureza=_procurar(raiz, "NFe/infNFe/ide/natOp"),
        tipo_emissao=_procurar(raiz, "NFe/infNFe/ide/tpEmis"),
        ambiente=_procurar(raiz, "NFe/infNFe/ide/tpAmb"),
        emitente_nome=_procurar(raiz, "NFe/infNFe/emit/xNome"),
        emitente_documento=_documento(
            _procurar(raiz, "NFe/infNFe/emit/CNPJ") or _procurar(raiz, "NFe/infNFe/emit/CPF")
        ),
        emitente_ie=_procurar(raiz, "NFe/infNFe/emit/IE"),
        emitente_endereco=emitente_endereco,
        emitente_municipio_uf=emitente_municipio_uf,
        emitente_cep=emitente_cep,
        emitente_telefone=_procurar(raiz, "NFe/infNFe/emit/enderEmit/fone"),
        destinatario_nome=_procurar(raiz, "NFe/infNFe/dest/xNome"),
        destinatario_documento=_documento(
            _procurar(raiz, "NFe/infNFe/dest/CNPJ") or _procurar(raiz, "NFe/infNFe/dest/CPF")
        ),
        destinatario_ie=_procurar(raiz, "NFe/infNFe/dest/IE"),
        destinatario_endereco=destinatario_endereco,
        destinatario_municipio_uf=destinatario_municipio_uf,
        destinatario_cep=destinatario_cep,
        destinatario_telefone=_procurar(raiz, "NFe/infNFe/dest/enderDest/fone"),
        base_icms=_moeda(_procurar(raiz, "NFe/infNFe/total/ICMSTot/vBC")),
        valor_icms=_moeda(_procurar(raiz, "NFe/infNFe/total/ICMSTot/vICMS")),
        base_icms_st=_moeda(_procurar(raiz, "NFe/infNFe/total/ICMSTot/vBCST")),
        valor_icms_st=_moeda(_procurar(raiz, "NFe/infNFe/total/ICMSTot/vST")),
        valor_produtos=_moeda(_procurar(raiz, "NFe/infNFe/total/ICMSTot/vProd")),
        valor_frete=_moeda(_procurar(raiz, "NFe/infNFe/total/ICMSTot/vFrete")),
        valor_seguro=_moeda(_procurar(raiz, "NFe/infNFe/total/ICMSTot/vSeg")),
        valor_desconto=_moeda(_procurar(raiz, "NFe/infNFe/total/ICMSTot/vDesc")),
        valor_outras=_moeda(_procurar(raiz, "NFe/infNFe/total/ICMSTot/vOutro")),
        valor_ipi=_moeda(_procurar(raiz, "NFe/infNFe/total/ICMSTot/vIPI")),
        valor_total=_moeda(_procurar(raiz, "NFe/infNFe/total/ICMSTot/vNF")),
        transportador_nome=_procurar(raiz, "NFe/infNFe/transp/transporta/xNome"),
        transportador_documento=_documento(
            _procurar(raiz, "NFe/infNFe/transp/transporta/CNPJ")
            or _procurar(raiz, "NFe/infNFe/transp/transporta/CPF")
        ),
        transportador_ie=_procurar(raiz, "NFe/infNFe/transp/transporta/IE"),
        transportador_endereco=transportador_endereco,
        transportador_municipio_uf=transportador_municipio_uf,
        modalidade_frete=MODALIDADES_FRETE.get(modalidade, modalidade),
        informacoes_adicionais=_procurar(raiz, "NFe/infNFe/infAdic/infCpl"),
    )

    # Itens
    for det in raiz.iter():
        if local(det.tag) != "det":
            continue
        item = ItemNfe(
            codigo=_procurar(det, "prod/cProd"),
            descricao=_procurar(det, "prod/xProd"),
            ncm=_procurar(det, "prod/NCM"),
            cfop=_procurar(det, "prod/CFOP"),
            unidade=_procurar(det, "prod/uCom"),
            quantidade=_procurar(det, "prod/qCom"),
            valor_unitario=_moeda(_procurar(det, "prod/vUnCom")),
            valor_total=_moeda(_procurar(det, "prod/vProd")),
        )
        nota.itens.append(item)

    # Volumes
    for vol in raiz.iter():
        if local(vol.tag) != "vol":
            continue
        nota.volumes.append(
            {
                "quantidade": _procurar(vol, "qVol"),
                "especie": _procurar(vol, "esp"),
                "marca": _procurar(vol, "marca"),
                "peso_liquido": _procurar(vol, "pesoL"),
                "peso_bruto": _procurar(vol, "pesoB"),
            }
        )

    obrigatorios = {
        "chave": nota.chave,
        "numero": nota.numero,
        "emitente_nome": nota.emitente_nome,
        "destinatario_nome": nota.destinatario_nome,
        "valor_total": nota.valor_total,
        "protocolo": nota.protocolo,
    }
    nota.ausentes = [campo for campo, valor in obrigatorios.items() if not valor]
    return nota


class _Desenho:
    def __init__(self, pdf: canvas.Canvas) -> None:
        self.pdf = pdf
        self.largura, self.altura = landscape(A4)
        self.margem = 8 * mm
        self.y = self.altura - self.margem

    def bloco(self, titulo: str, linhas: list[tuple[str, str]], altura: float) -> None:
        util = self.largura - 2 * self.margem
        self.pdf.setFillColor(CINZA)
        self.pdf.rect(self.margem, self.y - 4.4 * mm, util, 4.8 * mm, fill=1, stroke=0)
        self.pdf.setFillColor(ESCURO)
        self.pdf.setFont("Helvetica-Bold", 7)
        self.pdf.drawString(self.margem + 1.5 * mm, self.y - 3.2 * mm, titulo)
        self.y -= 6 * mm

        topo = self.y + 2 * mm
        for rotulo, valor in linhas:
            if not valor:
                continue
            self.pdf.setFont("Helvetica", 6)
            self.pdf.setFillColor(colors.HexColor("#555555"))
            self.pdf.drawString(self.margem + 1.5 * mm, self.y, rotulo)
            self.pdf.setFont("Helvetica-Bold", 7.2)
            self.pdf.setFillColor(ESCURO)
            self.pdf.drawString(self.margem + 30 * mm, self.y, valor[:150])
            self.y -= 3.6 * mm
        self.pdf.setStrokeColor(LINHA)
        self.pdf.rect(self.margem, topo - altura * mm + 2 * mm, util, altura * mm, fill=0, stroke=1)
        self.y -= 3 * mm

    def tabela_itens(self, itens: list[ItemNfe]) -> None:
        util = self.largura - 2 * self.margem
        colunas = [
            ("CÓDIGO", 24, "codigo"),
            ("DESCRIÇÃO", 88, "descricao"),
            ("NCM", 20, "ncm"),
            ("CFOP", 14, "cfop"),
            ("UN", 12, "unidade"),
            ("QTD", 18, "quantidade"),
            ("V. UNIT", 22, "valor_unitario"),
            ("V. TOTAL", 24, "valor_total"),
        ]
        self.pdf.setFillColor(CINZA)
        self.pdf.rect(self.margem, self.y - 4.4 * mm, util, 4.8 * mm, fill=1, stroke=0)
        self.pdf.setFillColor(ESCURO)
        self.pdf.setFont("Helvetica-Bold", 6.5)
        x = self.margem + 1.5 * mm
        for rotulo, largura, _ in colunas:
            self.pdf.drawString(x, self.y - 3.2 * mm, rotulo)
            x += largura * mm
        self.y -= 6 * mm

        self.pdf.setFont("Helvetica", 6.8)
        for item in itens[:14]:
            x = self.margem + 1.5 * mm
            for _, largura, campo in colunas:
                valor = getattr(item, campo)
                limite = int(largura * 1.6)
                self.pdf.drawString(x, self.y, str(valor)[:limite])
                x += largura * mm
            self.y -= 3.4 * mm
        if len(itens) > 14:
            self.pdf.setFont("Helvetica-Oblique", 6.5)
            self.pdf.drawString(
                self.margem + 1.5 * mm,
                self.y,
                f"... mais {len(itens) - 14} item(ns) — continuação em outra folha",
            )
            self.y -= 3.4 * mm


def gerar_danfe_a4(dados: DadosDanfeA4) -> bytes:
    """Gera o DANFE A4 (paisagem) em PDF."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
    pdf.setTitle(f"DANFE {dados.chave}")

    desenho = _Desenho(pdf)

    # Cabeçalho
    pdf.setFont("Helvetica-Bold", 12)
    pdf.setFillColor(ESCURO)
    pdf.drawString(desenho.margem, desenho.y, "DANFE")
    pdf.setFont("Helvetica", 6.6)
    pdf.drawString(
        desenho.margem,
        desenho.y - 4 * mm,
        "Documento Auxiliar da Nota Fiscal Eletrônica — o XML autorizado prevalece sobre este impresso",
    )
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawRightString(
        desenho.largura - desenho.margem,
        desenho.y,
        f"NF-e {dados.numero}  Série {dados.serie}  Modelo {dados.modelo}",
    )
    pdf.setFont("Helvetica", 7)
    pdf.drawRightString(
        desenho.largura - desenho.margem,
        desenho.y - 4 * mm,
        f"Operação {dados.operacao}   Emissão {dados.emissao}",
    )
    desenho.y -= 9 * mm

    # Chave + protocolo
    pdf.setFont("Helvetica", 6.2)
    pdf.setFillColor(colors.HexColor("#555555"))
    pdf.drawString(desenho.margem, desenho.y, "CHAVE DE ACESSO")
    pdf.setFont("Helvetica-Bold", 7)
    pdf.setFillColor(ESCURO)
    pdf.drawString(desenho.margem + 26 * mm, desenho.y, dados.chave or "—")
    pdf.setFont("Helvetica", 6.2)
    pdf.setFillColor(colors.HexColor("#555555"))
    pdf.drawString(desenho.margem + 150 * mm, desenho.y, "PROTOCOLO")
    pdf.setFont("Helvetica-Bold", 7)
    pdf.setFillColor(ESCURO)
    pdf.drawString(desenho.margem + 170 * mm, desenho.y, dados.protocolo or "—")
    desenho.y -= 4 * mm
    if dados.chave:
        barra = code128.Code128(dados.chave, barHeight=8 * mm, barWidth=0.42)
        barra.drawOn(pdf, desenho.margem, desenho.y - 8 * mm)
        desenho.y -= 10 * mm

    desenho.bloco(
        "EMITENTE",
        [
            ("NOME/RAZÃO SOCIAL", dados.emitente_nome),
            ("CNPJ/CPF", dados.emitente_documento),
            ("INSCRIÇÃO ESTADUAL", dados.emitente_ie),
            ("ENDEREÇO", dados.emitente_endereco),
            ("MUNICÍPIO/UF", f"{dados.emitente_municipio_uf}  CEP {dados.emitente_cep}".strip()),
        ],
        26,
    )
    desenho.bloco(
        "DESTINATÁRIO / REMETENTE",
        [
            ("NOME/RAZÃO SOCIAL", dados.destinatario_nome),
            ("CNPJ/CPF", dados.destinatario_documento),
            ("INSCRIÇÃO ESTADUAL", dados.destinatario_ie),
            ("ENDEREÇO", dados.destinatario_endereco),
            (
                "MUNICÍPIO/UF",
                f"{dados.destinatario_municipio_uf}  CEP {dados.destinatario_cep}".strip(),
            ),
            ("NATUREZA DA OPERAÇÃO", dados.natureza),
        ],
        30,
    )
    desenho.bloco(
        "CÁLCULO DO IMPOSTO",
        [
            ("BASE ICMS", dados.base_icms),
            ("VALOR ICMS", dados.valor_icms),
            ("BASE ICMS ST", dados.base_icms_st),
            ("VALOR ICMS ST", dados.valor_icms_st),
            ("VALOR PRODUTOS", dados.valor_produtos),
            ("VALOR FRETE", dados.valor_frete),
            ("VALOR SEGURO", dados.valor_seguro),
            ("DESCONTO", dados.valor_desconto),
            ("OUTRAS DESPESAS", dados.valor_outras),
            ("VALOR IPI", dados.valor_ipi),
            ("VALOR TOTAL DA NOTA", dados.valor_total),
        ],
        44,
    )
    desenho.bloco(
        "TRANSPORTADOR / VOLUMES TRANSPORTADOS",
        [
            ("NOME/RAZÃO SOCIAL", dados.transportador_nome),
            ("CNPJ/CPF", dados.transportador_documento),
            ("INSCRIÇÃO ESTADUAL", dados.transportador_ie),
            ("ENDEREÇO", dados.transportador_endereco),
            ("MUNICÍPIO/UF", dados.transportador_municipio_uf),
            ("MODALIDADE DO FRETE", dados.modalidade_frete),
            (
                "VOLUMES",
                "; ".join(
                    " ".join(
                        filter(
                            None,
                            [
                                f"{v.get('quantidade') or ''} {v.get('especie') or ''}".strip(),
                                f"marca {v['marca']}" if v.get("marca") else "",
                                f"peso líq. {v['peso_liquido']} kg"
                                if v.get("peso_liquido")
                                else "",
                                f"peso bruto {v['peso_bruto']} kg" if v.get("peso_bruto") else "",
                            ],
                        )
                    )
                    for v in dados.volumes
                ),
            ),
        ],
        34,
    )

    desenho.tabela_itens(dados.itens)

    if dados.informacoes_adicionais:
        desenho.bloco(
            "DADOS ADICIONAIS",
            [("INFORMAÇÕES COMPLEMENTARES", dados.informacoes_adicionais)],
            12,
        )

    pdf.setFont("Helvetica", 5.8)
    pdf.setFillColor(colors.HexColor("#666666"))
    pdf.drawString(
        desenho.margem,
        5 * mm,
        "Gerado localmente por open_notas_br. Leiaute [A VALIDAR] contra o MOC vigente; "
        "o XML autorizado prevalece.",
    )
    if dados.ausentes:
        pdf.drawString(
            desenho.margem,
            2.5 * mm,
            f"Campos não encontrados no XML: {', '.join(dados.ausentes)}",
        )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
