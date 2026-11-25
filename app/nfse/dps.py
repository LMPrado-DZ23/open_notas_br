"""Montagem da DPS (Declaração de Prestação de Serviço) — leiaute 1.01.

Estrutura e ordem dos elementos seguem a implementação de referência em Python
analisada em `docs/REFERENCIAS.md` (seção 7). O construtor **valida forma**
(dígitos, faixa, obrigatoriedade estrutural) e deixa a validação semântica para a
SEFIN, que responde com código de rejeição. Reprovar localmente o que a SEFIN
aceitaria é pior do que receber a rejeição: esconde a regra real.

Ponto que muda o desenho: **a DPS não carrega alíquotas nem valores de IBS/CBS.**
Ela declara `CST`, `cClassTrib`, `cIndOp` e `indDest`; a SEFIN calcula e devolve
os valores em `infNFSe/IBSCBS`. Por isso o motor tributário alimenta a simulação
e a conferência, não o XML enviado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from xml.etree import ElementTree as ET

from app.db.models.enums import AmbienteFiscal
from app.nfse.constants import (
    NS_NFSE,
    SERIE_API_MAX,
    SERIE_API_MIN,
    VERSAO_LEIAUTE,
    leiaute,
    tp_amb,
)
from notasbr.cadastros import apenas_digitos, normalizar_cnpj

ET.register_namespace("", NS_NFSE)

_RE_MUNICIPIO = re.compile(r"^\d{7}$")
_RE_CTRIBNAC = re.compile(r"^\d{6}$")
_RE_CINDOP = re.compile(r"^\d{6}$")
_RE_CCLASSTRIB = re.compile(r"^\d{6}$")
_RE_NBS = re.compile(r"^\d{9}$")

#: `opSimpNac`: 1 = não optante, 2 = MEI, 3 = ME/EPP.
OP_SIMP_NAC = frozenset({"1", "2", "3"})
#: `regEspTrib` (0 = nenhum).
REG_ESP_TRIB = frozenset(str(i) for i in range(7))
#: `tribISSQN`: 1 tributável, 2 imunidade, 3 exportação, 4 não incidência.
TRIB_ISSQN = frozenset({"1", "2", "3", "4"})
#: `tpRetISSQN`: 1 não retido, 2 retido pelo tomador, 3 retido pelo intermediário.
TP_RET_ISSQN = frozenset({"1", "2", "3"})
#: `tpEmit`: 1 prestador, 2 tomador, 3 intermediário.
TP_EMIT = frozenset({"1", "2", "3"})

VER_APLIC_PADRAO = "notasbr-1.0"


class ErroDps(Exception):
    """DPS inválida para montagem (falha de forma, não de negócio)."""


@dataclass(slots=True)
class Endereco:
    """Endereço nacional, no formato que a DPS exige."""

    logradouro: str
    numero: str
    bairro: str
    codigo_municipio: str  # IBGE, 7 dígitos
    uf: str  # 2 letras
    cep: str
    complemento: str | None = None


@dataclass(slots=True)
class Prestador:
    """Prestador do serviço e seu regime tributário."""

    documento: str  # CNPJ (ou CPF)
    op_simp_nac: str = "1"
    reg_esp_trib: str = "0"
    reg_ap_trib_sn: str | None = None
    inscricao_municipal: str | None = None
    telefone: str | None = None
    email: str | None = None


@dataclass(slots=True)
class Tomador:
    """Tomador (ou destinatário) do serviço."""

    nome: str
    documento: str | None = None  # CNPJ/CPF; ausente em não identificado
    email: str | None = None
    endereco: Endereco | None = None


@dataclass(slots=True)
class Tributacao:
    """Grupo `valores/trib`."""

    trib_issqn: str = "1"
    tp_ret_issqn: str = "1"
    p_aliq: Decimal | None = None
    cst_pis_cofins: str | None = None
    p_tot_trib_fed: Decimal | None = None
    p_tot_trib_est: Decimal | None = None
    p_tot_trib_mun: Decimal | None = None
    p_tot_trib_sn: Decimal | None = None


@dataclass(slots=True)
class Ibscbs:
    """Grupo `IBSCBS` da Reforma Tributária.

    Só a classificação viaja na DPS. Alíquota e valor são calculados pela SEFIN.
    """

    c_ind_op: str  # indicador da operação, 6 dígitos
    c_class_trib: str  # classificação tributária, 6 dígitos
    c_nbs: str  # código NBS do serviço, 9 dígitos
    ind_dest: str = "1"  # 1 = tomador é o destinatário
    ind_final: str | None = None  # 0 = não, 1 = sim (consumidor final)
    tp_oper: str | None = None
    destinatario: Tomador | None = None


@dataclass(slots=True)
class DpsInput:
    """Entrada completa para montar uma DPS."""

    ambiente: AmbienteFiscal
    c_mun_emissor: str
    serie: int
    n_dps: int
    dh_emi: datetime
    prestador: Prestador
    c_trib_nac: str
    x_desc_serv: str
    valor: Decimal
    tributacao: Tributacao = field(default_factory=Tributacao)
    tomador: Tomador | None = None
    c_trib_mun: str | None = None
    c_loc_prestacao: str | None = None
    v_desc_incond: Decimal | None = None
    v_desc_cond: Decimal | None = None
    ibscbs: Ibscbs | None = None
    tp_emit: str = "1"
    ver_aplic: str = VER_APLIC_PADRAO


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def id_dps(c_mun: str, documento: str, serie: str | int, n_dps: int) -> str:
    """Identificador da DPS: 45 posições.

    ``DPS`` + cMun(7) + tpInsc(1) + inscrição(14) + série(5) + nDPS(15).
    ``tpInsc``: 1 para CPF (11 dígitos), 2 para CNPJ.
    """
    doc = (
        normalizar_cnpj(documento)
        if len(normalizar_cnpj(documento)) == 14
        else apenas_digitos(documento)
    )
    if not doc:
        raise ErroDps("documento do prestador ausente: é ele que define o Id da DPS")
    tp_insc = "1" if len(doc) == 11 else "2"
    return f"DPS{c_mun}{tp_insc}{doc.zfill(14)}{int(serie):05d}{int(n_dps):015d}"


def formatar_decimal(valor: Decimal | None) -> str | None:
    """Formata com 2 casas e ponto decimal, como o leiaute exige."""
    if valor is None:
        return None
    quantizado = valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{quantizado:.2f}"


def _decimal(valor: object | None) -> Decimal | None:
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor))
    except InvalidOperation as exc:
        raise ErroDps(f"valor numérico inválido: {valor!r}") from exc


def _sub(pai: ET.Element, tag: str, texto: str | None = None) -> ET.Element:
    elemento = ET.SubElement(pai, f"{{{NS_NFSE}}}{tag}")
    if texto is not None:
        elemento.text = texto
    return elemento


def _opt(pai: ET.Element, tag: str, texto: str | None) -> None:
    if texto not in (None, ""):
        _sub(pai, tag, texto)


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------
def _validar(entrada: DpsInput) -> None:
    if not _RE_MUNICIPIO.match(entrada.c_mun_emissor or ""):
        raise ErroDps(
            f"código do município emissor inválido: {entrada.c_mun_emissor!r} (7 dígitos)"
        )

    serie = int(entrada.serie)
    if not SERIE_API_MIN <= serie <= SERIE_API_MAX:
        raise ErroDps(
            f"série {serie} fora da faixa permitida para emissão por sistema próprio "
            f"({SERIE_API_MIN}-{SERIE_API_MAX}); a série 70000 é do Emissor Web"
        )
    if entrada.n_dps < 1:
        raise ErroDps("número da DPS deve ser maior que zero")
    if entrada.dh_emi.tzinfo is None:
        raise ErroDps("dhEmi precisa de fuso horário: data sem fuso muda o dia da competência")
    valor = _decimal(entrada.valor)
    if valor is None or valor <= 0:
        raise ErroDps("valor do serviço deve ser maior que zero")
    if not (entrada.x_desc_serv or "").strip():
        raise ErroDps("descrição do serviço é obrigatória")
    if len(entrada.x_desc_serv) > 2000:
        raise ErroDps("descrição do serviço acima de 2000 caracteres")

    if not _RE_CTRIBNAC.match(entrada.c_trib_nac or ""):
        raise ErroDps(f"cTribNac inválido: {entrada.c_trib_nac!r} (6 dígitos)")
    if entrada.c_trib_mun and not entrada.c_trib_mun.isdigit():
        raise ErroDps(f"cTribMun inválido: {entrada.c_trib_mun!r}")

    prest = entrada.prestador
    if prest.op_simp_nac not in OP_SIMP_NAC:
        raise ErroDps(f"opSimpNac inválido: {prest.op_simp_nac!r} (1, 2 ou 3)")
    if prest.reg_esp_trib not in REG_ESP_TRIB:
        raise ErroDps(f"regEspTrib inválido: {prest.reg_esp_trib!r}")
    if prest.op_simp_nac == "3" and not prest.reg_ap_trib_sn:
        raise ErroDps("ME/EPP do Simples (opSimpNac=3) exige regApTribSN")

    trib = entrada.tributacao
    if trib.trib_issqn not in TRIB_ISSQN:
        raise ErroDps(f"tribISSQN inválido: {trib.trib_issqn!r} (1 a 4)")
    if trib.tp_ret_issqn not in TP_RET_ISSQN:
        raise ErroDps(f"tpRetISSQN inválido: {trib.tp_ret_issqn!r} (1, 2 ou 3)")

    if entrada.tomador is not None:
        if not (entrada.tomador.nome or "").strip():
            raise ErroDps("nome do tomador é obrigatório quando o tomador é informado")
        if entrada.tomador.documento:
            doc = normalizar_cnpj(entrada.tomador.documento)
            if len(doc) not in (11, 14):
                raise ErroDps(f"documento do tomador inválido: {entrada.tomador.documento!r}")
        if entrada.tomador.endereco is not None:
            _validar_endereco(entrada.tomador.endereco, "tomador")

    if entrada.ibscbs is not None:
        ibs = entrada.ibscbs
        if not _RE_CINDOP.match(ibs.c_ind_op or ""):
            raise ErroDps(f"cIndOp do IBS/CBS inválido: {ibs.c_ind_op!r} (6 dígitos)")
        if not _RE_CCLASSTRIB.match(ibs.c_class_trib or ""):
            raise ErroDps(f"cClassTrib do IBS/CBS inválido: {ibs.c_class_trib!r} (6 dígitos)")
        if not _RE_NBS.match(ibs.c_nbs or ""):
            raise ErroDps("com IBS/CBS o código NBS do serviço é obrigatório (9 dígitos)")
        if ibs.ind_dest not in {"0", "1"}:
            raise ErroDps(f"indDest inválido: {ibs.ind_dest!r} (0 ou 1)")
        if ibs.destinatario is not None:
            _validar_endereco(ibs.destinatario.endereco, "destinatário")


def _validar_endereco(endereco: Endereco | None, papel: str) -> None:
    if endereco is None:
        return
    if not _RE_MUNICIPIO.match(endereco.codigo_municipio or ""):
        raise ErroDps(f"código do município do {papel} inválido: {endereco.codigo_municipio!r}")
    if not re.fullmatch(r"[A-Z]{2}", endereco.uf or ""):
        raise ErroDps(f"UF do {papel} inválida: {endereco.uf!r}")
    if not apenas_digitos(endereco.cep) or len(apenas_digitos(endereco.cep)) != 8:
        raise ErroDps(f"CEP do {papel} inválido: {endereco.cep!r}")


# ---------------------------------------------------------------------------
# Blocos
# ---------------------------------------------------------------------------
def _pessoa(pai: ET.Element, tag: str, pessoa: Tomador) -> None:
    """Bloco de pessoa (tomador/destinatário/intermediário)."""
    elemento = _sub(pai, tag)
    doc = normalizar_cnpj(pessoa.documento) if pessoa.documento else ""
    if doc and len(doc) == 14:
        _sub(elemento, "CNPJ", doc)
    elif doc and len(doc) == 11:
        _sub(elemento, "CPF", doc)
    _opt(elemento, "xNome", pessoa.nome.strip()[:300])
    _opt(elemento, "email", pessoa.email)

    if pessoa.endereco is not None:
        end = _sub(elemento, "end")
        nac = _sub(end, "endNac")
        _sub(nac, "cMun", pessoa.endereco.codigo_municipio)
        _sub(nac, "CEP", apenas_digitos(pessoa.endereco.cep))
        _sub(end, "xLgr", pessoa.endereco.logradouro.strip()[:255])
        _sub(end, "nro", pessoa.endereco.numero.strip()[:60])
        _opt(end, "xCpl", pessoa.endereco.complemento)
        _sub(end, "xBairro", pessoa.endereco.bairro.strip()[:60])


def _prestador(pai: ET.Element, prestador: Prestador) -> None:
    elemento = _sub(pai, "prest")
    doc = normalizar_cnpj(prestador.documento)
    if len(doc) == 14:
        _sub(elemento, "CNPJ", doc)
    elif len(doc) == 11:
        _sub(elemento, "CPF", doc)
    else:
        raise ErroDps(f"documento do prestador inválido: {prestador.documento!r}")

    _opt(elemento, "IM", prestador.inscricao_municipal)
    _opt(elemento, "fone", apenas_digitos(prestador.telefone) or None)
    _opt(elemento, "email", prestador.email)

    regime = _sub(elemento, "regTrib")
    _sub(regime, "opSimpNac", prestador.op_simp_nac)
    if prestador.op_simp_nac == "3":
        _opt(regime, "regApTribSN", prestador.reg_ap_trib_sn)
    _sub(regime, "regEspTrib", prestador.reg_esp_trib)


def _tributos(pai: ET.Element, entrada: DpsInput) -> None:
    trib = entrada.tributacao
    grupo = _sub(pai, "trib")
    municipal = _sub(grupo, "tribMun")
    _sub(municipal, "tribISSQN", trib.trib_issqn)
    _sub(municipal, "tpRetISSQN", trib.tp_ret_issqn)
    aliquota = formatar_decimal(_decimal(trib.p_aliq))
    if aliquota is not None:
        _sub(municipal, "pAliq", aliquota)

    total = _sub(grupo, "totTrib")
    if entrada.prestador.op_simp_nac == "1":
        # Não optante do Simples: pTotTribSN e indTotTrib são proibidos.
        percentuais = _sub(total, "pTotTrib")
        _sub(
            percentuais,
            "pTotTribFed",
            formatar_decimal(_decimal(trib.p_tot_trib_fed) or Decimal(0)) or "0.00",
        )
        _sub(
            percentuais,
            "pTotTribEst",
            formatar_decimal(_decimal(trib.p_tot_trib_est) or Decimal(0)) or "0.00",
        )
        _sub(
            percentuais,
            "pTotTribMun",
            formatar_decimal(_decimal(trib.p_tot_trib_mun) or Decimal(0)) or "0.00",
        )
    elif entrada.prestador.op_simp_nac == "3" and trib.p_tot_trib_sn is not None:
        _sub(total, "pTotTribSN", formatar_decimal(_decimal(trib.p_tot_trib_sn)))
    else:
        # MEI não pode informar pTotTribSN; ME/EPP sem percentual usa indTotTrib.
        _sub(total, "indTotTrib", "0")


def _ibscbs(pai: ET.Element, entrada: DpsInput, nt009: bool) -> None:
    """Grupo IBS/CBS: classificação apenas, sem alíquota nem valor."""
    ibs = entrada.ibscbs
    assert ibs is not None

    grupo = _sub(pai, "IBSCBS")
    if not nt009:
        # Na NT 009 `finNFSe` sai daqui e vai para `infDPS`.
        _sub(grupo, "finNFSe", "0")
    _opt(grupo, "indFinal", ibs.ind_final)
    _sub(grupo, "cIndOp", ibs.c_ind_op)
    _opt(grupo, "tpOper", ibs.tp_oper)
    _sub(grupo, "indDest", ibs.ind_dest)
    if ibs.destinatario is not None:
        _pessoa(grupo, "dest", ibs.destinatario)

    valores = _sub(grupo, "valores")
    trib = _sub(valores, "trib")
    alvo = trib if nt009 else _sub(trib, "gIBSCBS")
    _sub(alvo, "CST", ibs.c_class_trib[:3])
    _sub(alvo, "cClassTrib", ibs.c_class_trib)


# ---------------------------------------------------------------------------
# Construção
# ---------------------------------------------------------------------------
def construir_dps(entrada: DpsInput) -> ET.Element:
    """Monta o elemento `DPS` completo, não assinado."""
    _validar(entrada)

    nt009 = leiaute(entrada.ambiente, entrada.dh_emi) == "v1_01_nt009"
    raiz = ET.Element(f"{{{NS_NFSE}}}DPS")
    raiz.set("versao", VERSAO_LEIAUTE)

    inf = _sub(raiz, "infDPS")
    inf.set(
        "Id",
        id_dps(entrada.c_mun_emissor, entrada.prestador.documento, entrada.serie, entrada.n_dps),
    )

    _sub(inf, "tpAmb", tp_amb(entrada.ambiente))
    _sub(inf, "dhEmi", entrada.dh_emi.replace(microsecond=0).isoformat())
    _sub(inf, "verAplic", entrada.ver_aplic)
    _sub(inf, "serie", str(int(entrada.serie)))
    _sub(inf, "nDPS", str(int(entrada.n_dps)))
    _sub(inf, "dCompet", entrada.dh_emi.date().isoformat())
    _sub(inf, "tpEmit", entrada.tp_emit)
    if nt009:
        _sub(inf, "finNFSe", "0")
    _sub(inf, "cLocEmi", entrada.c_mun_emissor)

    _prestador(inf, entrada.prestador)
    if entrada.tomador is not None:
        _pessoa(inf, "toma", entrada.tomador)

    servico = _sub(inf, "serv")
    local = _sub(servico, "locPrest")
    _sub(local, "cLocPrestacao", entrada.c_loc_prestacao or entrada.c_mun_emissor)

    c_serv = _sub(servico, "cServ")
    _sub(c_serv, "cTribNac", entrada.c_trib_nac)
    _opt(c_serv, "cTribMun", entrada.c_trib_mun)
    if nt009:
        # Na NT 009 o NBS vem antes da descrição.
        _opt(c_serv, "cNBS", entrada.ibscbs.c_nbs if entrada.ibscbs else None)
        _sub(c_serv, "xDescServ", entrada.x_desc_serv.strip())
    else:
        _sub(c_serv, "xDescServ", entrada.x_desc_serv.strip())
        _opt(c_serv, "cNBS", entrada.ibscbs.c_nbs if entrada.ibscbs else None)

    valores = _sub(inf, "valores")
    prestacao = _sub(valores, "vServPrest")
    _sub(prestacao, "vServ", formatar_decimal(_decimal(entrada.valor)))

    if entrada.v_desc_incond or entrada.v_desc_cond:
        descontos = _sub(valores, "vDescCondIncond")
        _opt(descontos, "vDescIncond", formatar_decimal(_decimal(entrada.v_desc_incond)))
        _opt(descontos, "vDescCond", formatar_decimal(_decimal(entrada.v_desc_cond)))

    _tributos(valores, entrada)

    if entrada.ibscbs is not None:
        _ibscbs(inf, entrada, nt009)

    return raiz


def dps_para_bytes(entrada: DpsInput) -> bytes:
    """Serializa a DPS em UTF-8 com declaração XML."""
    raiz = construir_dps(entrada)
    # A declaração é escrita à mão de propósito: `ET.tostring(xml_declaration=True)`
    # emite aspas SIMPLES (`encoding='UTF-8'`), e o validador da SEFIN procura o
    # literal com aspas duplas — a DPS foi recusada com E1229 ("Xml não está
    # utilizando codificação UTF-8") por causa disso. Ver docs/REFERENCIAS.md §14.
    corpo = ET.tostring(raiz, encoding="UTF-8")
    return b'<?xml version="1.0" encoding="UTF-8"?>' + corpo


def extrair_id(dps_xml: bytes) -> str | None:
    """Lê o `Id` de `infDPS` de uma DPS já montada."""
    try:
        raiz = ET.fromstring(dps_xml)
    except ET.ParseError:
        return None
    for elemento in raiz.iter():
        if elemento.tag.endswith("infDPS"):
            return elemento.get("Id")
    return None
