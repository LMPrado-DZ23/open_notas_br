"""Catálogo fiscal: procedência obrigatória e cobertura medida."""

from __future__ import annotations

import pytest
from app.catalogo import (
    UFS,
    ErroDeImportacao,
    aplicar_endpoints_sefaz,
    medir_cobertura,
    planejar_endpoints_sefaz,
    validar_linha,
    validar_lote,
)

LINHA = {
    "uf": "GO",
    "ambiente": "2",
    "servico": "NFeAutorizacao",
    "url": "https://homolog.sefaz.go.gov.br/nfe",
    "versao_soap": "1.2",
    "fonte_url": "https://www.sefaz.go.gov.br/nfe/manual.pdf",
    "autorizador": "GO",
}


class TestValidacao:
    def test_linha_valida(self) -> None:
        linha = validar_linha(LINHA, linha=1)
        assert linha.uf == "GO"
        assert linha.ambiente == "2"

    def test_uf_minuscula_e_normalizada(self) -> None:
        assert validar_linha({**LINHA, "uf": "go"}, linha=1).uf == "GO"

    def test_uf_inexistente_recusada(self) -> None:
        with pytest.raises(ErroDeImportacao, match="UF inválida"):
            validar_linha({**LINHA, "uf": "XX"}, linha=1)

    def test_url_http_recusada(self) -> None:
        with pytest.raises(ErroDeImportacao, match="https"):
            validar_linha({**LINHA, "url": "http://x.example/nfe"}, linha=1)

    def test_fonte_http_recusada(self) -> None:
        # A fonte também precisa ser verificável; fonte em texto claro não é.
        with pytest.raises(ErroDeImportacao, match="https"):
            validar_linha({**LINHA, "fonte_url": "http://x.example/manual"}, linha=1)

    def test_sem_fonte_recusa(self) -> None:
        # R8: endpoint sem procedência é chute.
        with pytest.raises(ErroDeImportacao, match="fonte_url"):
            validar_linha({k: v for k, v in LINHA.items() if k != "fonte_url"}, linha=1)

    def test_ambiente_invalido_recusado(self) -> None:
        with pytest.raises(ErroDeImportacao, match="ambiente"):
            validar_linha({**LINHA, "ambiente": "3"}, linha=1)

    def test_servico_desconhecido_recusado(self) -> None:
        with pytest.raises(ErroDeImportacao, match="serviço desconhecido"):
            validar_linha({**LINHA, "servico": "ServicoInventado"}, linha=1)

    def test_versao_soap_invalida_recusada(self) -> None:
        with pytest.raises(ErroDeImportacao, match="versao_soap"):
            validar_linha({**LINHA, "versao_soap": "2.0"}, linha=1)


class TestLote:
    def test_erro_numa_linha_nao_descarta_as_outras(self) -> None:
        validas, erros = validar_lote([LINHA, {**LINHA, "uf": "XX"}])
        assert len(validas) == 1
        assert len(erros) == 1

    def test_duplicata_no_arquivo_e_erro(self) -> None:
        # Duplicata ambígua: qual vence? Nenhuma.
        validas, erros = validar_lote([LINHA, LINHA])
        assert len(validas) == 1
        assert any("repetido" in e for e in erros)

    def test_vazia_nao_explode(self) -> None:
        validas, erros = validar_lote([])
        assert validas == [] and erros == []


class TestUfs:
    def test_sao_27(self) -> None:
        assert len(UFS) == 27

    def test_sem_repeticao(self) -> None:
        assert len(set(UFS)) == len(UFS)

    def test_todas_com_duas_letras(self) -> None:
        assert all(len(uf) == 2 and uf.isupper() for uf in UFS)


class TestBanco:
    async def test_insere_e_nao_duplica(self, sessao_db) -> None:
        validas, _ = validar_lote([LINHA])
        plano = await planejar_endpoints_sefaz(sessao_db, validas)
        assert len(plano.inserir) == 1

        await aplicar_endpoints_sefaz(sessao_db, plano, dry_run=False)
        await sessao_db.commit()

        plano2 = await planejar_endpoints_sefaz(sessao_db, validas)
        assert len(plano2.inserir) == 0
        assert len(plano2.inalterado) == 1

    async def test_url_diferente_vira_atualizacao(self, sessao_db) -> None:
        validas, _ = validar_lote([LINHA])
        await aplicar_endpoints_sefaz(
            sessao_db, await planejar_endpoints_sefaz(sessao_db, validas), dry_run=False
        )
        await sessao_db.commit()

        nova, _ = validar_lote([{**LINHA, "url": "https://novo.example/nfe"}])
        plano = await planejar_endpoints_sefaz(sessao_db, nova)
        assert len(plano.atualizar) == 1
        assert len(plano.inserir) == 0

    async def test_dry_run_nao_grava(self, sessao_db) -> None:
        validas, _ = validar_lote([LINHA])
        plano = await planejar_endpoints_sefaz(sessao_db, validas)
        await aplicar_endpoints_sefaz(sessao_db, plano, dry_run=True)
        await sessao_db.commit()

        depois = await planejar_endpoints_sefaz(sessao_db, validas)
        assert len(depois.inserir) == 1, "dry-run não pode gravar"


class TestCobertura:
    async def test_banco_vazio_reporta_27_sem_cobertura(self, sessao_db) -> None:
        cobertura = await medir_cobertura(sessao_db)
        assert len(cobertura.ufs_com_autorizacao) == 0
        assert len(cobertura.ufs_sem_autorizacao) == 27
        assert cobertura.percentual == 0.0

    async def test_uma_uf_configurada_aparece(self, sessao_db) -> None:
        validas, _ = validar_lote([LINHA])
        await aplicar_endpoints_sefaz(
            sessao_db, await planejar_endpoints_sefaz(sessao_db, validas), dry_run=False
        )
        await sessao_db.commit()

        cobertura = await medir_cobertura(sessao_db)
        assert cobertura.ufs_com_autorizacao == ("GO",)
        assert len(cobertura.ufs_sem_autorizacao) == 26
        assert 3.5 < cobertura.percentual < 3.8
