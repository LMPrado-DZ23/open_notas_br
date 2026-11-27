"""Extração de `cStat` da NFS-e autorizada (§78).

Defeito medido em 2026-11-27: `fiscal_documents.codigo_status` era **NULL em todos os registros**,
inclusive na NFS-e real autorizada cujo XML carrega `cStat=100`. O código de autorização existia
apenas dentro do blob guardado — perguntar "esta nota está autorizada?" exigia abrir e interpretar o
XML.

Estes testes fixam: extração com namespace, ausência do campo, XML inválido e a persistência no
documento. **Não** testam `nProt`: a NFS-e Nacional não emite número de protocolo como a NF-e, e
inventar um seria pior que deixar nulo.
"""

from __future__ import annotations

from app.nfse.errors import extrair_cstat

XML_AUTORIZADO = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<NFSe versao="1.01" xmlns="http://www.sped.fazenda.gov.br/nfse">'
    "<infNFSe><nNFSe>2</nNFSe><cStat>100</cStat>"
    "<dhProc>2026-11-25T20:21:46-03:00</dhProc><nDFSe>44</nDFSe></infNFSe></NFSe>"
)


class TestExtracao:
    def test_le_cstat_com_namespace(self) -> None:
        assert extrair_cstat(XML_AUTORIZADO) == "100"

    def test_aceita_bytes(self) -> None:
        assert extrair_cstat(XML_AUTORIZADO.encode()) == "100"

    def test_sem_cstat_devolve_none(self) -> None:
        assert extrair_cstat("<NFSe><infNFSe/></NFSe>") is None

    def test_xml_invalido_nao_levanta(self) -> None:
        """Documento já autorizado não pode virar erro de leitura depois."""
        assert extrair_cstat("não é xml") is None

    def test_vazio_devolve_none(self) -> None:
        assert extrair_cstat(None) is None
        assert extrair_cstat(b"") is None


class TestPersistencia:
    async def test_emissao_grava_codigo_status(self, cliente, sessao_db) -> None:
        from tests.test_fase2_certificado import SENHA, gerar_pfx

        criado = await cliente.post("/v1/tenants", json={"slug": "cstat-1", "nome": "Cstat LTDA"})
        tenant = criado.json()
        cabecalho = {"X-API-Key": tenant["api_key"]}
        await cliente.put(
            "/v1/me/config-fiscal",
            json={
                "municipio_ibge": "5200258",
                "uf": "GO",
                "ambiente": "homologacao",
                "codigo_tributacao_nacional": "010701",
                "serie_dps": "1",
                "aliquota_iss": 0.05,
            },
            headers=cabecalho,
        )
        await cliente.post(
            "/v1/me/certificados",
            files={"arquivo": ("c.pfx", gerar_pfx(), "application/x-pkcs12")},
            data={"senha": SENHA.decode(), "apelido": "a1"},
            headers=cabecalho,
        )

        emitida = await cliente.post(
            "/v1/emissoes",
            json={"idempotency_key": "cstat-0001", "valor": "10.00", "descricao": "Servico"},
            headers=cabecalho,
        )
        assert emitida.status_code == 201, emitida.text

        # A leitura acontece pelo banco: a rota de documento não expõe `codigo_status` no contrato.
        from app.db.models.invoice import FiscalDocument
        from sqlalchemy import select

        registros = (
            (
                await sessao_db.execute(
                    select(FiscalDocument).where(FiscalDocument.tenant_id == tenant["id"])
                )
            )
            .scalars()
            .all()
        )
        assert registros, "emissão deveria ter criado documento"
        assert registros[0].codigo_status == "100", "cStat autorizado precisa ficar consultável"
        assert registros[0].protocolo is None, (
            "NFS-e Nacional não tem número de protocolo; preencher seria inventar"
        )
