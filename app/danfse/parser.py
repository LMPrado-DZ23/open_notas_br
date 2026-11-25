"""Extração do DANFSe a partir do XML autorizado da NFS-e.

Estratégia deliberada: **busca por nome local com caminhos candidatos**, não por
caminho único. Motivo concreto:

1. O XML da NFS-e nacional tem `infNFSe` com grupos opcionais; o caminho exato de
   um campo pode variar com o leiaute (v1.01 vs NT 009).
2. A implementação de referência faz o mesmo: procura o campo em várias fontes
   (`addrSources.find(s => s.xLgr)`) em vez de fixar um caminho.
3. Fixar um único caminho falha em silêncio: o campo aparece vazio no PDF sem
   ninguém perceber. Aqui, o que não for encontrado entra em `ausentes` e é
   impresso como aviso no rodapé — falha visível, nunca silenciosa.

Os caminhos são **[A VALIDAR]** contra um XML autorizado real: foram montados a
partir do leiaute 1.01 e do modelo de campos da NT 008, não de uma nota real.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.danfse.model import (
    DanfseData,
    Pessoa,
    Totais,
    TributacaoFederal,
    TributacaoIbsCbs,
    TributacaoIssqn,
)
from notasbr.xml_util import local, parse_seguro, texto

NS_NFSE = "http://www.sped.fazenda.gov.br/nfse"

#: Caminhos candidatos por campo. A ordem é a de preferência.
CAMINHOS: dict[str, tuple[str, ...]] = {
    "numero": ("infNFSe/nNFSe", "NFSe/infNFSe/nNFSe"),
    "competencia": ("infNFSe/DPS/infDPS/dCompet", "infNFSe/infDPS/dCompet"),
    "data_processamento": ("infNFSe/dhProc",),
    "numero_dps": ("infNFSe/DPS/infDPS/nDPS", "infNFSe/infDPS/nDPS"),
    "serie_dps": ("infNFSe/DPS/infDPS/serie", "infNFSe/infDPS/serie"),
    "data_emissao_dps": ("infNFSe/DPS/infDPS/dhEmi", "infNFSe/infDPS/dhEmi"),
    "situacao": ("infNFSe/cStat",),
    "finalidade": ("infNFSe/finNFSe", "infNFSe/DPS/infDPS/finNFSe"),
    "ambiente": ("infNFSe/ambGer", "infNFSe/DPS/infDPS/tpAmb"),
    "municipio": ("infNFSe/cLocIncid",),
    "prestador_doc": (
        "infNFSe/emit/CNPJ",
        "infNFSe/emit/CPF",
        "infNFSe/DPS/infDPS/prest/CNPJ",
        "infNFSe/DPS/infDPS/prest/CPF",
    ),
    "prestador_nome": ("infNFSe/emit/xNome", "infNFSe/DPS/infDPS/prest/xNome"),
    "prestador_im": ("infNFSe/emit/IM", "infNFSe/DPS/infDPS/prest/IM"),
    "prestador_telefone": ("infNFSe/emit/fone", "infNFSe/DPS/infDPS/prest/fone"),
    "prestador_email": ("infNFSe/emit/email", "infNFSe/DPS/infDPS/prest/email"),
    "tomador_doc": ("infNFSe/DPS/infDPS/toma/CNPJ", "infNFSe/DPS/infDPS/toma/CPF"),
    "tomador_nome": ("infNFSe/DPS/infDPS/toma/xNome",),
    "tomador_email": ("infNFSe/DPS/infDPS/toma/email",),
    "servico_codigo": ("infNFSe/DPS/infDPS/serv/cServ/cTribNac",),
    "servico_nbs": ("infNFSe/DPS/infDPS/serv/cServ/cNBS",),
    "servico_descricao": ("infNFSe/DPS/infDPS/serv/cServ/xDescServ",),
    "local_prestacao": ("infNFSe/DPS/infDPS/serv/locPrest/cLocPrestacao",),
    "issqn_trib": ("infNFSe/DPS/infDPS/valores/trib/tribMun/tribISSQN",),
    "issqn_ret": ("infNFSe/DPS/infDPS/valores/trib/tribMun/tpRetISSQN",),
    "issqn_aliq": ("infNFSe/DPS/infDPS/valores/trib/tribMun/pAliq",),
    "ret_irrf": ("infNFSe/DPS/infDPS/valores/trib/tribFed/vRetIRRF",),
    "ret_cp": ("infNFSe/DPS/infDPS/valores/trib/tribFed/vRetCP",),
    "ret_csll": ("infNFSe/DPS/infDPS/valores/trib/tribFed/vRetCSLL",),
    "valor_servico": (
        "infNFSe/DPS/infDPS/valores/vServPrest/vServ",
        "infNFSe/valores/vServPrest/vServ",
    ),
    "desconto_incond": ("infNFSe/DPS/infDPS/valores/vDescCondIncond/vDescIncond",),
    "desconto_cond": ("infNFSe/DPS/infDPS/valores/vDescCondIncond/vDescCond",),
    "valor_liquido": ("infNFSe/valores/vLiq", "infNFSe/valores/vLiqNfse"),
    # IBS/CBS — vem da SEFIN, não da DPS
    "ibs_cst": ("infNFSe/IBSCBS/valores/trib/gIBSCBS/CST",),
    "ibs_class": ("infNFSe/IBSCBS/valores/trib/gIBSCBS/cClassTrib",),
    "ibs_base": ("infNFSe/IBSCBS/valores/trib/gIBSCBS/vBC",),
    "ibs_total": ("infNFSe/IBSCBS/valores/trib/gIBSCBS/vIBSTot",),
    "ibs_uf": ("infNFSe/IBSCBS/valores/trib/gIBSCBS/gIBSUF/vIBSUF",),
    "ibs_mun": ("infNFSe/IBSCBS/valores/trib/gIBSCBS/gIBSMun/vIBSMun",),
    "cbs_valor": ("infNFSe/IBSCBS/valores/trib/gIBSCBS/gCBS/vCBS",),
    "p_ibs_uf": ("infNFSe/IBSCBS/valores/trib/gIBSCBS/gIBSUF/pIBSUF",),
    "p_ibs_mun": ("infNFSe/IBSCBS/valores/trib/gIBSCBS/gIBSMun/pIBSMun",),
    "p_cbs": ("infNFSe/IBSCBS/valores/trib/gIBSCBS/gCBS/pCBS",),
    "ibs_cbs_total": ("infNFSe/IBSCBS/valores/vTotIBSCBS",),
}


#: Nome do campo extraído -> atributo em `DanfseData`.
#: Existe porque o nome no leiaute (`cTribNac`) e o nome no modelo
#: (`codigo_tributacao`) não são os mesmos, e mapear explicitamente é mais
#: seguro que renomear o modelo para acompanhar o XML.
MAPA_MODELO: dict[str, str] = {
    "servico_codigo": "codigo_tributacao",
    "servico_nbs": "codigo_nbs",
    "servico_descricao": "descricao_servico",
}


def _procurar(raiz, caminhos: tuple[str, ...]) -> str | None:
    """Primeiro valor não vazio entre os caminhos candidatos."""
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


def _pessoa(raiz, prefixo: str) -> Pessoa | None:
    """Monta uma pessoa a partir dos campos com o prefixo informado."""
    documento = _procurar(raiz, CAMINHOS.get(f"{prefixo}_doc", ())) or ""
    nome = _procurar(raiz, CAMINHOS.get(f"{prefixo}_nome", ())) or ""
    if not documento and not nome:
        return None

    # O endereço fica no PAI do campo de documento. Dentro de `end`, os campos
    # de logradouro são IRMÃOS de `endNac` (que só carrega cMun/CEP), não filhos
    # dele. Alguns leiautes trazem o endereço sem o grupo `end`.
    bases = tuple(caminho.rsplit("/", 1)[0] for caminho in CAMINHOS.get(f"{prefixo}_doc", ()))
    endereco_partes: list[str] = []
    for sufixo in ("xLgr", "nro", "xCpl", "xBairro"):
        candidatos: list[str] = []
        for base in bases:
            candidatos.extend((f"{base}/end/{sufixo}", f"{base}/{sufixo}"))
        valor = _procurar(raiz, tuple(candidatos))
        if valor:
            endereco_partes.append(valor)

    return Pessoa(
        documento=documento,
        nome=nome,
        inscricao_municipal=_procurar(raiz, CAMINHOS.get(f"{prefixo}_im", ())) or "",
        telefone=_procurar(raiz, CAMINHOS.get(f"{prefixo}_telefone", ())) or "",
        email=_procurar(raiz, CAMINHOS.get(f"{prefixo}_email", ())) or "",
        endereco=", ".join(endereco_partes),
    )


def _moeda(valor: str | None) -> str:
    """Normaliza número para exibição com 2 casas, sem inventar valor."""
    if not valor:
        return ""
    try:
        return f"{Decimal(valor):.2f}".replace(".", ",")
    except (InvalidOperation, ValueError):
        return valor


_RE_CHAVE = re.compile(r"^NFS(.+)$")


def extrair_chave(raiz) -> str:
    """Chave da NFS-e, do atributo `Id` de `infNFSe` (prefixo `NFS` removido)."""
    for elemento in raiz.iter():
        if local(elemento.tag) == "infNFSe":
            identificador = elemento.get("Id") or ""
            achado = _RE_CHAVE.match(identificador)
            return achado.group(1) if achado else identificador
    return ""


def parse_danfse(xml: bytes | str) -> DanfseData:
    """Extrai o modelo do DANFSe a partir do XML autorizado.

    Levanta :class:`~notasbr.erros.XmlInvalido` se o conteúdo não for XML legível.
    """
    dados_bytes = xml.encode("utf-8") if isinstance(xml, str) else xml
    raiz = parse_seguro(dados_bytes)

    dados = DanfseData()
    dados.chave_acesso = extrair_chave(raiz)

    for campo in (
        "numero",
        "competencia",
        "data_processamento",
        "numero_dps",
        "serie_dps",
        "data_emissao_dps",
        "situacao",
        "finalidade",
        "ambiente",
        "municipio",
        "servico_codigo",
        "servico_nbs",
        "servico_descricao",
        "local_prestacao",
    ):
        valor = _procurar(raiz, CAMINHOS[campo])
        atributo = MAPA_MODELO.get(campo, campo)
        if valor:
            setattr(dados, atributo, valor)
        else:
            dados.ausentes.append(campo)

    dados.prestador = _pessoa(raiz, "prestador") or Pessoa()
    dados.tomador = _pessoa(raiz, "tomador")

    dados.issqn = TributacaoIssqn(
        trib_issqn=_procurar(raiz, CAMINHOS["issqn_trib"]) or "",
        retencao=_procurar(raiz, CAMINHOS["issqn_ret"]) or "",
        aliquota=_procurar(raiz, CAMINHOS["issqn_aliq"]) or "",
        nao_sujeito=(_procurar(raiz, CAMINHOS["issqn_trib"]) or "") == "4",
    )
    dados.federal = TributacaoFederal(
        ret_irrf=_moeda(_procurar(raiz, CAMINHOS["ret_irrf"])),
        ret_cp=_moeda(_procurar(raiz, CAMINHOS["ret_cp"])),
        ret_csll=_moeda(_procurar(raiz, CAMINHOS["ret_csll"])),
    )

    valor_servico = _procurar(raiz, CAMINHOS["valor_servico"])
    valor_liquido = _procurar(raiz, CAMINHOS["valor_liquido"])
    dados.totais = Totais(
        valor_servico=_moeda(valor_servico),
        desconto_incondicionado=_moeda(_procurar(raiz, CAMINHOS["desconto_incond"])),
        desconto_condicionado=_moeda(_procurar(raiz, CAMINHOS["desconto_cond"])),
        valor_liquido=_moeda(valor_liquido),
    )

    dados.ibscbs = TributacaoIbsCbs(
        cst_class=" / ".join(
            filter(
                None,
                [
                    _procurar(raiz, CAMINHOS["ibs_cst"]),
                    _procurar(raiz, CAMINHOS["ibs_class"]),
                ],
            )
        ),
        base_calculo=_moeda(_procurar(raiz, CAMINHOS["ibs_base"])),
        aliquota_ibs_uf=_procurar(raiz, CAMINHOS["p_ibs_uf"]) or "",
        aliquota_ibs_mun=_procurar(raiz, CAMINHOS["p_ibs_mun"]) or "",
        valor_ibs_uf=_moeda(_procurar(raiz, CAMINHOS["ibs_uf"])),
        valor_ibs_mun=_moeda(_procurar(raiz, CAMINHOS["ibs_mun"])),
        total_ibs=_moeda(_procurar(raiz, CAMINHOS["ibs_total"])),
        aliquota_cbs=_procurar(raiz, CAMINHOS["p_cbs"]) or "",
        valor_cbs=_moeda(_procurar(raiz, CAMINHOS["cbs_valor"])),
        total_ibs_cbs=_moeda(_procurar(raiz, CAMINHOS["ibs_cbs_total"])),
    )

    dados.versao_layout = raiz.get("versao") or ""

    return dados
