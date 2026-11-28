"""Ramos do auditor e das regras de documento (estrutura e chave) sem cobertura.

Cada caso parte do fixture autoconsistente de `tests.construir` e aplica **uma** mutação, para
que o desfecho observado seja atribuível a ela. Nas regras que dependem da chave decomposta o
DV é recalculado e a chave nova é escrita no documento inteiro (`Id` do `infNFe` e `chNFe` do
protocolo): mexer só num bloco da chave faria o parser recusá-la e a regra nem rodaria.

O foco aqui são os desfechos **silenciosos** — a regra que pula ou retorna sem avaliar —, porque
é neles que um "aprovado" pode nascer de um campo que ninguém olhou.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from notasbr import Severidade, auditar_bytes
from notasbr.xml_util import local, navegar
from tests.construir import com_atributo, com_campo, cte, nfe, sem_campo, transformar
from tests.test_regras_chave import _recom_dv


def _codigos(relatorio, severidade: Severidade | None = None) -> set[str]:
    achados = relatorio.achados if severidade is None else relatorio.por_severidade(severidade)
    return {a.codigo for a in achados}


def _puladas(relatorio) -> set[str]:
    return {p.codigo for p in relatorio.puladas}


def _motivo_da_pulada(relatorio, codigo: str) -> str:
    return next(p.motivo for p in relatorio.puladas if p.codigo == codigo)


def _chave_nova(xml: bytes, posicao: int, valor: str) -> bytes:
    """Troca `valor` na posição indicada da chave, recalcula o DV e reescreve o documento."""
    chave = auditar_bytes(xml).chave
    assert chave is not None, "o caso precisa de um documento com chave de acesso"
    nova = _recom_dv(chave[:posicao] + valor + chave[posicao + len(valor) : 43])
    assert len(nova) == 44
    return xml.replace(chave.encode(), nova.encode())


def _trocar_documento(xml: bytes, grupo: str, tag: str, valor: str) -> bytes:
    """Substitui CNPJ/CPF/idEstrangeiro de `grupo` por `tag` com `valor`."""

    def mutar(raiz: ET.Element) -> None:
        elemento = navegar(raiz, grupo)
        assert elemento is not None, f"grupo inexistente no fixture: {grupo}"
        for filho in list(elemento):
            if local(filho.tag) in {"CNPJ", "CPF", "idEstrangeiro"}:
                elemento.remove(filho)
        novo = ET.SubElement(elemento, tag)
        novo.text = valor

    return transformar(xml, mutar)


class TestResumosDoRelatorio:
    def test_emitente_ausente_vira_dict_vazio(self) -> None:
        xml = sem_campo(nfe(), "NFe/infNFe/emit")

        relatorio = auditar_bytes(xml)

        assert relatorio.emitente == {}
        assert relatorio.to_dict()["documento"]["emitente"] is None

    def test_emitente_com_cpf_e_formatado(self) -> None:
        xml = _trocar_documento(nfe(), "NFe/infNFe/emit", "CPF", "11144477735")

        emitente = auditar_bytes(xml).emitente

        assert emitente["cpf"] == "111.444.777-35"
        assert "cnpj" not in emitente

    def test_destinatario_ausente_vira_dict_vazio(self) -> None:
        xml = sem_campo(nfe(), "NFe/infNFe/dest")

        relatorio = auditar_bytes(xml)

        assert relatorio.destinatario == {}
        assert relatorio.to_dict()["documento"]["destinatario"] is None

    def test_destinatario_com_cpf_e_formatado(self) -> None:
        xml = _trocar_documento(nfe(), "NFe/infNFe/dest", "CPF", "11144477735")

        destinatario = auditar_bytes(xml).destinatario

        assert destinatario["cpf"] == "111.444.777-35"
        assert "cnpj" not in destinatario

    def test_destinatario_estrangeiro_e_preservado(self) -> None:
        xml = _trocar_documento(nfe(), "NFe/infNFe/dest", "idEstrangeiro", "EX-001")

        destinatario = auditar_bytes(xml).destinatario

        assert destinatario["id_estrangeiro"] == "EX-001"
        assert "cnpj" not in destinatario
        assert "cpf" not in destinatario


class TestEstrutura:
    def test_versao_ausente_vira_erro_de_versao(self) -> None:
        """Sem `versao` no corpo nem na raiz, DOC-VER-001 é erro — não o aviso de versão estranha."""

        def mutar(raiz: ET.Element) -> None:
            raiz.attrib.pop("versao", None)
            corpo = navegar(raiz, "NFe/infNFe")
            assert corpo is not None
            corpo.attrib.pop("versao", None)

        xml = transformar(nfe(), mutar)
        achados = [a for a in auditar_bytes(xml).achados if a.codigo == "DOC-VER-001"]

        assert [a.severidade for a in achados] == [Severidade.ERRO]
        assert "ausente" in achados[0].mensagem

    def test_item_sem_nitem_vira_erro(self) -> None:
        def mutar(raiz: ET.Element) -> None:
            item = navegar(raiz, "NFe/infNFe/det")
            assert item is not None
            item.attrib.pop("nItem")

        xml = transformar(nfe(), mutar)
        mensagens = [a.mensagem for a in auditar_bytes(xml).achados if a.codigo == "NFE-DET-001"]

        assert any("sem atributo nItem" in mensagem for mensagem in mensagens)

    def test_nitem_nao_inteiro_vira_erro(self) -> None:
        xml = com_atributo(nfe(), "NFe/infNFe/det", "nItem", "1a")
        achado = next(a for a in auditar_bytes(xml).achados if a.codigo == "NFE-DET-001")

        assert "não é inteiro" in achado.mensagem
        assert achado.detalhe["nItem"] == "1a"

    def test_consumidor_final_sem_dest_vira_aviso(self) -> None:
        xml = sem_campo(nfe(), "NFe/infNFe/dest")
        avisos = [a for a in auditar_bytes(xml).achados if a.codigo == "NFE-DEST-001"]

        assert [a.severidade for a in avisos] == [Severidade.AVISO]
        assert "consumidor final" in avisos[0].mensagem

    def test_cte_sem_toma_rem_dest_vira_erro(self) -> None:
        xml = sem_campo(sem_campo(cte(), "CTe/infCte/rem"), "CTe/infCte/dest")

        assert "CTE-TOMADOR-001" in _codigos(auditar_bytes(xml), Severidade.ERRO)


class TestChave:
    def test_campo_ausente_no_ide_nao_entra_na_conferencia(self) -> None:
        """`serie` ausente não vira divergência: a conferência só compara o que existe."""
        xml = sem_campo(nfe(), "NFe/infNFe/ide/serie")
        relatorio = auditar_bytes(xml)

        assert "CHAVE-CONSIST-001" not in _codigos(relatorio)
        # A ausência tem regra própria, e é ela que responde.
        assert "OBRIG-ide-serie" in _codigos(relatorio, Severidade.ERRO)

    def test_emitente_sem_documento_nao_acusa_divergencia(self) -> None:
        xml = sem_campo(nfe(), "NFe/infNFe/emit/CNPJ")
        relatorio = auditar_bytes(xml)

        assert "CHAVE-EMIT-001" not in _codigos(relatorio)
        assert "OBRIG-emit-CNPJ" in _codigos(relatorio, Severidade.ERRO)

    def test_contingencia_pula_aamm_contra_dhemi(self) -> None:
        """tpEmis != 1 na chave: o AAMM pode mesmo divergir de `dhEmi`, e a regra pula."""
        xml = _chave_nova(nfe(), 34, "2")
        xml = com_campo(xml, "NFe/infNFe/ide/tpEmis", "2")
        relatorio = auditar_bytes(xml)

        assert "CHAVE-AMM-002" in _puladas(relatorio)
        assert "contingência" in _motivo_da_pulada(relatorio, "CHAVE-AMM-002")
        assert "CHAVE-AMM-002" not in _codigos(relatorio)

    def test_dhemi_curto_nao_avalia_aamm(self) -> None:
        """Sem 7 caracteres não há AAMM legível em `dhEmi`: a regra não avalia nem acusa."""
        xml = com_campo(nfe(), "NFe/infNFe/ide/dhEmi", "2025")
        relatorio = auditar_bytes(xml)

        assert "CHAVE-AMM-002" not in _codigos(relatorio)
        assert "CHAVE-AMM-002" not in _puladas(relatorio)

    def test_dhemi_nao_numerico_vira_aviso(self) -> None:
        xml = com_campo(nfe(), "NFe/infNFe/ide/dhEmi", "20XX-01-15T10:30:00-03:00")
        achados = [a for a in auditar_bytes(xml).achados if a.codigo == "CHAVE-AMM-002"]

        assert len(achados) == 1
        assert achados[0].severidade is Severidade.AVISO
        assert "formato reconhecível" in achados[0].mensagem

    def test_protocolo_sem_chave_pula_prot(self) -> None:
        """Protocolo presente, mas nenhuma chave legível: PROT-001 pula em vez de comparar."""

        def mutar(raiz: ET.Element) -> None:
            corpo = navegar(raiz, "NFe/infNFe")
            assert corpo is not None
            corpo.attrib.pop("Id", None)
            info = navegar(raiz, "protNFe/infProt")
            assert info is not None
            for filho in list(info):
                if local(filho.tag) == "chNFe":
                    info.remove(filho)

        xml = transformar(nfe(), mutar)
        relatorio = auditar_bytes(xml)

        assert "PROT-001" in _puladas(relatorio)
        assert "chave ausente" in _motivo_da_pulada(relatorio, "PROT-001")
        # A ausência não fica sem resposta: o formato da chave é cobrado.
        assert "CHAVE-FMT-001" in _codigos(relatorio, Severidade.ERRO)

    def test_tpamb_ausente_nao_avalia_ambiente(self) -> None:
        xml = sem_campo(nfe(), "NFe/infNFe/ide/tpAmb")
        relatorio = auditar_bytes(xml)

        assert "AMB-001" not in _codigos(relatorio)
        assert "OBRIG-ide-tpAmb" in _codigos(relatorio, Severidade.ERRO)
