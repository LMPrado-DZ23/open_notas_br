"""Chave de acesso de 44 dígitos (NF-e, NFC-e, CT-e, MDF-e, CT-e OS).

Layout fixo, da esquerda para a direita::

    cUF(2) AAMM(4) CNPJ(14) mod(2) serie(3) nNF(9) tpEmis(1) cNF(8) DV(1)

O DV é módulo 11 com pesos 2..9 aplicados da direita para a esquerda sobre os 43
primeiros dígitos. Resto < 2 resulta em 0; caso contrário o DV é ``11 - resto``.

Este módulo não inventa: se um documento usar outro layout (a NFS-e, por
exemplo, não usa esta chave), ele não é aceito aqui.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cadastros import apenas_digitos
from .erros import ChaveInvalida

TAMANHO_CHAVE = 44

#: Códigos IBGE de UF usados na posição `cUF` da chave.
UFS: dict[str, str] = {
    "11": "RO",
    "12": "AC",
    "13": "AM",
    "14": "RR",
    "15": "PA",
    "16": "AP",
    "17": "TO",
    "21": "MA",
    "22": "PI",
    "23": "CE",
    "24": "RN",
    "25": "PB",
    "26": "PE",
    "27": "AL",
    "28": "SE",
    "29": "BA",
    "31": "MG",
    "32": "ES",
    "33": "RJ",
    "35": "SP",
    "41": "PR",
    "42": "SC",
    "43": "RS",
    "50": "MS",
    "51": "MT",
    "52": "GO",
    "53": "DF",
}

#: Modelos de documento fiscal que usam a chave de 44 dígitos.
MODELOS: dict[str, str] = {
    "55": "NF-e",
    "65": "NFC-e",
    "57": "CT-e",
    "58": "MDF-e",
    "67": "CT-e OS",
}

#: Modelo -> tipo interno usado pelo auditor.
TIPO_POR_MODELO: dict[str, str] = {
    "55": "nfe",
    "65": "nfe",
    "57": "cte",
    "67": "cte",
}

#: Forma de emissão. 1 é o caso normal; os demais são contingência.
FORMAS_EMISSAO: dict[str, str] = {
    "1": "Normal",
    "2": "FS-IA (contingência)",
    "3": "SCAN",
    "4": "DPEC",
    "5": "FS-DA",
    "6": "SVC-AN",
    "7": "SVC-RS",
    "9": "Offline (NFC-e)",
}

#: Ambientes da SEFAZ.
AMBIENTES: dict[str, str] = {
    "1": "Produção",
    "2": "Homologação",
}

_PESOS_DV = (2, 3, 4, 5, 6, 7, 8, 9)


def calcular_dv(primeiros_43: str) -> str:
    """Calcula o DV de uma chave a partir dos 43 primeiros dígitos."""
    base = apenas_digitos(primeiros_43)
    if len(base) != TAMANHO_CHAVE - 1:
        raise ValueError(f"o cálculo do DV espera {TAMANHO_CHAVE - 1} dígitos, recebeu {len(base)}")
    soma = 0
    # Da direita para a esquerda, ciclando os pesos 2..9.
    for posicao, caractere in enumerate(reversed(base)):
        soma += int(caractere) * _PESOS_DV[posicao % len(_PESOS_DV)]
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def chave_valida(valor: str | None) -> bool:
    """True se tem 44 dígitos e o DV confere."""
    num = apenas_digitos(valor)
    if len(num) != TAMANHO_CHAVE:
        return False
    try:
        return calcular_dv(num[:43]) == num[43]
    except ValueError:  # pragma: no cover - tamanho já foi checado acima
        return False


def montar_chave(
    *,
    c_uf: str,
    aamm: str,
    cnpj: str,
    modelo: str,
    serie: str | int,
    numero: str | int,
    tp_emis: str = "1",
    c_nf: str,
) -> str:
    """Monta uma chave de 44 dígitos com os campos preenchidos à esquerda por zero.

    Útil para testes e para conferir uma chave calculada por outro sistema.
    """
    aamm = apenas_digitos(aamm)
    if len(aamm) != 4:
        raise ValueError(f"AAMM deve ter 4 dígitos, recebeu {len(aamm)!r}")
    partes = (
        apenas_digitos(c_uf).zfill(2),
        aamm,
        apenas_digitos(cnpj).zfill(14),
        apenas_digitos(modelo).zfill(2),
        apenas_digitos(str(serie)).zfill(3),
        apenas_digitos(str(numero)).zfill(9),
        apenas_digitos(tp_emis).zfill(1),
        apenas_digitos(c_nf).zfill(8),
    )
    base = "".join(partes)
    if len(base) != 43:
        raise ValueError(f"chave base deveria ter 43 dígitos, tem {len(base)}: {base!r}")
    return base + calcular_dv(base)


@dataclass(frozen=True, slots=True)
class ChaveAcesso:
    """Chave de acesso decomposta.

    `valor` é sempre a string de 44 dígitos. Construa com :meth:`parse` em vez de
    instanciar direto, para não manter uma chave inconsistente em memória.
    """

    valor: str
    c_uf: str
    aamm: str
    cnpj: str
    modelo: str
    serie: str
    numero: str
    tp_emis: str
    c_nf: str
    dv: str

    # -- construção ---------------------------------------------------
    @classmethod
    def parse(cls, valor: str) -> ChaveAcesso:
        """Decompõe a chave. Levanta :class:`ChaveInvalida` se a forma não bater."""
        num = apenas_digitos(valor)
        if len(num) != TAMANHO_CHAVE:
            raise ChaveInvalida(f"chave deve ter {TAMANHO_CHAVE} dígitos, recebeu {len(num)}")
        if calcular_dv(num[:43]) != num[43]:
            raise ChaveInvalida(f"dígito verificador não confere para a chave {num}")
        return cls(
            valor=num,
            c_uf=num[0:2],
            aamm=num[2:6],
            cnpj=num[6:20],
            modelo=num[20:22],
            serie=num[22:25],
            numero=num[25:34],
            tp_emis=num[34:35],
            c_nf=num[35:43],
            dv=num[43:44],
        )

    # -- leitura ------------------------------------------------------
    @property
    def uf(self) -> str | None:
        """Sigla da UF ou ``None`` se o código IBGE não for conhecido."""
        return UFS.get(self.c_uf)

    @property
    def modelo_nome(self) -> str | None:
        """Nome do modelo (``NF-e``, ``CT-e``...) ou ``None``."""
        return MODELOS.get(self.modelo)

    @property
    def tipo(self) -> str | None:
        """Tipo interno do documento (``nfe``, ``cte``) ou ``None``."""
        return TIPO_POR_MODELO.get(self.modelo)

    @property
    def ambiente_emissao(self) -> str | None:
        return FORMAS_EMISSAO.get(self.tp_emis)

    @property
    def ano(self) -> int:
        """Ano com 4 dígitos (``25`` vira ``2025``)."""
        return 2000 + int(self.aamm[:2])

    @property
    def mes(self) -> int:
        return int(self.aamm[2:])

    @property
    def numero_int(self) -> int:
        return int(self.numero)

    @property
    def serie_int(self) -> int | None:
        try:
            return int(self.serie)
        except ValueError:
            return None

    # -- apresentação -------------------------------------------------
    def formatada(self) -> str:
        """Agrupa em blocos de 4 dígitos: ``3525 0111 2223 ...``."""
        return " ".join(self.valor[i : i + 4] for i in range(0, TAMANHO_CHAVE, 4))

    def to_dict(self) -> dict[str, object]:
        return {
            "chave": self.valor,
            "c_uf": self.c_uf,
            "uf": self.uf,
            "aamm": self.aamm,
            "ano": self.ano,
            "mes": self.mes,
            "cnpj": self.cnpj,
            "modelo": self.modelo,
            "modelo_nome": self.modelo_nome,
            "serie": self.serie,
            "numero": self.numero,
            "tp_emis": self.tp_emis,
            "forma_emissao": self.ambiente_emissao,
            "c_nf": self.c_nf,
            "dv": self.dv,
        }

    def __str__(self) -> str:  # pragma: no cover - conveniência
        return self.valor
