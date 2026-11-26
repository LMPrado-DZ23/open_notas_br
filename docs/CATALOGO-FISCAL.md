# Catálogo fiscal: preparar SEFAZ de todos os estados e as prefeituras

Este documento descreve o que **existe** hoje, o que **não existe**, e como preencher sem
inventar nada. Leia junto de `docs/auditoria_inicial.md`.

## O que já está pronto

| Peça | Onde | Estado |
|---|---|---|
| Tabela de endpoints por UF/ambiente/serviço | `webservices_sefaz` (migration 0005 + 0008) | ✅ |
| Procedência obrigatória | `fonte_url` NOT NULL + CHECK `https://` | ✅ |
| Tabela de municípios (5571 reais, IBGE) | `municipios_nfse` (migration 0004) | ✅ |
| Fábrica de driver por município | `app/nfse/drivers_factory.py` | ✅ |
| Motor ABRASF + assinatura do RPS | `drivers_abrasf.py`, `assinatura_rps.py` | ✅ |
| Validação de lote com procedência | `app/catalogo/__init__.py` | ✅ |
| Importador com `dry-run` | `scripts/importar_catalogo.py` | ✅ |
| Relatório de cobertura medido | `scripts/cobertura_fiscal.py` | ✅ |

## O que NÃO existe, e por quê

**Nenhum endpoint de SEFAZ está cadastrado.** Nenhum município está homologado.

Isso não é falta de código. É falta de **dado com fonte**. O repositório não traz URLs de
autorizador porque:

- as URLs mudam por portaria, e uma cópia velha emite contra o lugar errado;
- os autorizadores são compartilhados (SVRS, SVAN) — a URL de uma UF não é "a URL daquela
  UF", e tratar assim quebra silenciosamente;
- R8 proíbe inventar endereço fiscal.

## Como preencher

### 1. SEFAZ (27 UFs)

Descubra as URLs no portal oficial da SEFAZ da UF ou do autorizador que a atende, e monte o
JSON no formato de `data/exemplos/endpoints_sefaz.exemplo.json`:

```json
{
  "uf": "GO",
  "ambiente": "2",
  "servico": "NFeAutorizacao",
  "url": "https://<endpoint real>",
  "versao_soap": "1.2",
  "versao_layout": "4.00",
  "fonte_url": "https://<onde isso está documentado>",
  "autorizador": "GO"
}
```

Serviços aceitos: `NFeAutorizacao`, `NFeRetAutorizacao`, `NFeStatusServico`,
`NFeDistribuicaoDFe`, `NFeRecepcaoEvento`, `NFeInutilizacao`, `CTeRecepcaoSinc`,
`CTeRecepcaoEvento`, `MDFeRecepcaoSinc`, `MDFeRecepcaoEvento`.

Valide sem gravar:

```
python -m scripts.importar_catalogo data/endpoints_sefaz.json
```

Grave só depois de conferir o plano:

```
python -m scripts.importar_catalogo data/endpoints_sefaz.json --aplicar
```

A importação **recusa**: UF inexistente, ambiente fora de `1`/`2`, serviço desconhecido,
`url` ou `fonte_url` que não seja `https://`, e duplicata `(uf, ambiente, serviço)` no mesmo
arquivo.

### 2. Prefeituras

O município já existe pelo IBGE. Falta `provedor`, `url_producao`, `url_homologacao`,
`namespace_xml`, `encoding`, `assina_rps`, `assina_lote` e `fonte_url`. A fábrica
(`criar_driver`) **recusa** município sem URL ou sem fonte — não há caminho que emita contra
URL suposta.

### 3. Confira a cobertura

```
python -m scripts.cobertura_fiscal
```

Saída medida hoje:

```
municípios cadastrados : 5571
com URL de produção    : 0
com fonte registrada   : 5571
homologados (testados) : 0

== SEFAZ (homologação) ==
UFs com autorização cadastrada: 0/27 (0.0%)
```

## Ordem recomendada de onboarding

1. **Uma UF em homologação**, começando por `NFeStatusServico` — é a chamada mais barata e
   prova certificado, URL e envelope juntos, sem emitir documento.
2. `NFeAutorizacao` com uma nota de teste.
3. `NFeRetAutorizacao` (recibo) se o autorizador for assíncrono.
4. `NFeRecepcaoEvento` (cancelamento, CC-e).
5. Demais serviços e outras UFs.
6. Municípios: um provedor por vez, com fixture e plano de homologação.

## Defeito encontrado ao preparar isto

A coluna `versao_soap` nasceu `VARCHAR(4)` na migration 0005, mas o SQLAlchemy grava o
**nome** do membro do enum (`SOAP_11`, 7 caracteres). Resultado: **nenhum** endpoint de
SEFAZ podia ser cadastrado — a preparação para todos os estados era impossível por largura
de coluna. Corrigido na migration 0008, com round-trip verificado.

---

## Fontes obtidas (2026-11-26)

Baixadas por `python -m scripts.baixar_fontes`, com SHA-256 e data em
`data/fontes/MANIFESTO.json`:

| Arquivo | Origem | Cobertura |
|---|---|---|
| `wsnfe_4.00_mod55.xml` | repositório oficial NFePHP (sped-nfe) | 15 autorizadores: AM AN BA GO MG MS MT PE PR RS SP SVAN SVRS SVCAN SVCRS |
| `wsnfe_4.00_mod65.xml` | idem | **28 entradas: as 27 UFs + SVRS** |

## BLOQUEIO ENCONTRADO: falta `modelo` na chave

`webservices_sefaz` tem chave única `(uf, ambiente, servico)` e **não tem coluna `modelo`**.
NF-e (55) e NFC-e (65) usam o mesmo nome de serviço (`NFeAutorizacao`) mas, em algumas UFs,
hosts diferentes. Medido nos arquivos baixados:

```
GO  homologacao: 55 = homolog.sefaz.go.gov.br/nfe/services/NFeAutorizacao4
                 65 = homolog.sefaz.go.gov.br/nfe/services/NFeAutorizacao4   (iguais)
SP  homologacao: 55 = homologacao.nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx
                 65 = homologacao.nfce.fazenda.sp.gov.br/ws/NFeAutorizacao4.asmx  (DIFERENTES)
```

**Consequência se importar agora**: cadastrar NFC-e depois de NF-e sobrescreveria o endpoint
de São Paulo, e a NF-e de SP passaria a ser enviada ao host da NFC-e. Falha silenciosa, com
recusa só no autorizador.

**Decisão**: não importar antes da migration que adiciona `modelo` (55/65) e recompõe a chave
única para `(uf, modelo, ambiente, servico)`. O importador e a cobertura passam a exigir
`modelo`, e a contagem de cobertura vira por modelo.

## Próximo passo, na ordem

1. Migration `0009`: `modelo` (55/65) em `webservices_sefaz`, com nova chave única.
2. Parser dos dois XML para o formato do importador, gravando `modelo`, `autorizador` e
   `fonte_url` = URL bruta do arquivo no GitHub + hash do manifesto.
3. Importar em homologação, rodar `cobertura_fiscal` e **testar `NFeStatusServico`** em uma
   UF antes de qualquer autorização.
4. NFS-e: endpoint único nacional (`sefin.nfse.gov.br`) cobre quem migrou; para provedores
   próprios, `ACBrNFSeXServicos.ini` do ACBr, com a mesma regra de procedência.

## Autorizadores virtuais não são UFs

`SVAN`, `SVRS`, `SVCAN`, `SVCRS` e `AN` aparecem nos arquivos como autorizadores. O
importador recusa sigla que não seja UF de propósito: guardar `uf="SVRS"` criaria uma linha
que nenhum tenant usa. A ligação "UF X é atendida pelo autorizador Y" precisa da tabela
oficial do Portal Nacional — **não foi obtida nesta execução**, e não será deduzida por
semelhança de nome.
