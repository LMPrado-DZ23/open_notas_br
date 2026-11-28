"""Cobertura de **todos** os estados e municípios — sem rede e sem amostragem.

O pedido "testar em todos os estados e municípios" não pode significar transmitir para 5.571
prefeituras: em NFS-e nacional o município entra como **código IBGE** no XML, e a emissão é feita no
ambiente nacional. O que dá para verificar de forma determinística, e é o que estes testes fazem:

1. os **5.571 municípios** do cache oficial do IBGE (`data/ibge_municipios.json`) têm código de 7
   dígitos, prefixo de UF coerente com a tabela oficial, nome não vazio e código único;
2. as **27 UFs** aparecem, e só elas;
3. o catálogo de endpoints SEFAZ (`data/endpoints_sefaz.json`) só referencia UF existente, modelo
   conhecido e URL https — UF fora do catálogo é caso de 503 documentado, não de URL inventada.

Limite declarado: emissão real por UF depende de autorizador e credenciamento; o catálogo versionado
tem 10 UFs de NF-e. Isso é testado como **dado**, não como transmissão.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
MUNICIPIOS = RAIZ / "data" / "ibge_municipios.json"
ENDPOINTS = RAIZ / "data" / "endpoints_sefaz.json"

#: Códigos oficiais de UF do IBGE (prefixo do código de município). Fonte: IBGE — estrutura do
#: código de município, 2 primeiros dígitos = UF.
PREFIXO_UF: dict[str, str] = {
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

UFS = frozenset(PREFIXO_UF.values())


def _municipios() -> list[dict[str, str]]:
    return json.loads(MUNICIPIOS.read_text(encoding="utf-8"))


def _endpoints() -> list[dict[str, str]]:
    return json.loads(ENDPOINTS.read_text(encoding="utf-8"))


class TestMunicipios:
    def test_cache_tem_todos_os_municipios_do_ibge(self) -> None:
        """A contagem não é fixada em 5.570: o teste exige cobertura plausível e cresce com a fonte."""
        municipios = _municipios()

        assert len(municipios) >= 5500, f"cache suspeito: {len(municipios)} municípios"
        assert len({m["codigo_ibge"] for m in municipios}) == len(municipios), "código duplicado"

    def test_todo_codigo_tem_sete_digitos(self) -> None:
        invalidos = [
            m["codigo_ibge"]
            for m in _municipios()
            if not (m["codigo_ibge"].isdigit() and len(m["codigo_ibge"]) == 7)
        ]

        assert not invalidos, (
            f"{len(invalidos)} código(s) fora do padrão de 7 dígitos: {invalidos[:5]}"
        )

    def test_prefixo_do_codigo_bate_com_a_uf_declarada(self) -> None:
        """UF trocada desloca competência e autorizador — erro caro e silencioso."""
        divergentes = [
            f"{m['codigo_ibge']} {m['uf']} (prefixo {m['codigo_ibge'][:2]} → {PREFIXO_UF.get(m['codigo_ibge'][:2], '?')})"
            for m in _municipios()
            if PREFIXO_UF.get(m["codigo_ibge"][:2]) != m["uf"]
        ]

        assert not divergentes, (
            f"{len(divergentes)} município(s) com UF incoerente: {divergentes[:5]}"
        )

    def test_nome_nao_vazio(self) -> None:
        vazios = [m["codigo_ibge"] for m in _municipios() if not str(m.get("nome", "")).strip()]

        assert not vazios, f"{len(vazios)} município(s) sem nome: {vazios[:5]}"

    def test_as_27_ufs_estao_presentes(self) -> None:
        presentes = {m["uf"] for m in _municipios()}

        assert presentes == UFS, (
            f"faltando: {sorted(UFS - presentes)} | sobrando: {sorted(presentes - UFS)}"
        )

    def test_cada_uf_tem_municipio(self) -> None:
        por_uf: dict[str, int] = {}
        for municipio in _municipios():
            por_uf[municipio["uf"]] = por_uf.get(municipio["uf"], 0) + 1

        sem_nada = sorted(uf for uf in UFS if por_uf.get(uf, 0) == 0)
        assert not sem_nada, f"UF sem município no cache: {sem_nada}"


class TestUfsDoCatalogo:
    def test_tabela_de_prefixo_cobre_as_27_ufs(self) -> None:
        assert len(PREFIXO_UF) == 27, "tabela de UF incompleta"
        assert len(set(PREFIXO_UF.values())) == 27, "duas UFs com o mesmo prefixo"

    def test_endpoints_so_referenciam_uf_existente(self) -> None:
        desconhecidas = sorted({e["uf"] for e in _endpoints()} - UFS)

        assert not desconhecidas, f"UF desconhecida no catálogo: {desconhecidas}"

    def test_endpoints_usam_https(self) -> None:
        inseguros = [e["url"] for e in _endpoints() if not e["url"].startswith("https://")]

        assert not inseguros, f"{len(inseguros)} endpoint(s) sem TLS: {inseguros[:3]}"

    def test_modelos_conhecidos(self) -> None:
        """Modelos: 55 NF-e, 57 CT-e, 58 MDF-e, 65 NFC-e, 67 CT-e OS.

        A primeira versão listava só 55/57/58 e **falhou** ao encontrar 65 — o dado estava certo e a
        expectativa errada. Registrado para ninguém "consertar" o catálogo depois.
        """
        conhecidos = {"55", "57", "58", "65", "67"}
        modelos = {e["modelo"] for e in _endpoints()}

        assert modelos <= conhecidos, f"modelo inesperado: {sorted(modelos - conhecidos)}"

    def test_sem_endpoint_duplicado(self) -> None:
        chaves = [(e["uf"], e["modelo"], e["ambiente"], e["servico"]) for e in _endpoints()]

        duplicados = {c for c in chaves if chaves.count(c) > 1}
        assert not duplicados, f"chave repetida no catálogo: {sorted(duplicados)[:3]}"

    def test_uf_sem_endpoint_e_caso_de_503_nao_de_url_inventada(self) -> None:
        """A rota declara 503 para UF fora do catálogo; o teste fixa a expectativa do dado."""
        com_endpoint = {e["uf"] for e in _endpoints()}

        assert len(com_endpoint) < 27, "se todos os UFs têm endpoint, revise a documentação de 503"
        assert com_endpoint <= UFS

    @pytest.mark.parametrize("uf", sorted(UFS))
    def test_uf_do_pais_e_reconhecida_pelo_catalogo_ou_ausente_de_proposito(self, uf: str) -> None:
        """Para cada uma das 27 UFs: ou tem endpoint https, ou não tem — nunca URL quebrada."""
        do_uf = [e for e in _endpoints() if e["uf"] == uf]

        assert all(e["url"].startswith("https://") for e in do_uf)
