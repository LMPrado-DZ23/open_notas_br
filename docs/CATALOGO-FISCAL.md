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

---

## Importação feita (2026-11-26)

`modelo` entrou na tabela e na chave (migration `0009`, round-trip verificado), e os dois
arquivos foram convertidos e importados:

```
python -m scripts.converter_wsurls           -> total=180 válidas=180 erros=0
python -m scripts.importar_catalogo data/endpoints_sefaz.json --aplicar
                                             -> gravado: 180 novo(s)
```

### Cobertura medida depois da importação

| Documento | Homologação | Produção |
|---|---|---|
| NF-e (55) | **10/27** (37,0%) | 10/27 |
| NFC-e (65) | **8/27** (29,6%) | 8/27 |

UFs sem cadastro em NF-e: AC AL AP CE DF ES MA PA PB PI RJ RN RO RR SC SE TO.

**Por que não são 27:** essas 17 UFs são atendidas por autorizador virtual (SVRS ou SVAN).
Os arquivos trazem o bloco do autorizador, não a linha de cada UF atendida. A ligação
"UF X → autorizador Y" está na tabela oficial do Portal Nacional e **não foi obtida**.
Não deduzi por semelhança de nome.

### Defeito encontrado ao importar

`ServicoSefaz` não tinha `NFeConsultaProtocolo`: 36 linhas (20% do arquivo) eram rejeitadas.
O serviço de consulta de protocolo é operação central — estava ausente do enum, não do
leiaute. Adicionado; o importador passou a aceitar 180/180.

### Registro de medição: o banco guarda o NOME do enum

`Filtering` por `servico='NFeAutorizacao'` em SQL cru devolve zero; o valor gravado é
`NFE_AUTORIZACAO`. Isso quase me fez reportar cobertura 0/27 depois de importar 180 linhas.
Query de conferência precisa do nome, não do valor.

### Pendência registrada, não corrigida

`alembic check` acusa drift **pré-existente** em `calculo_audit` (defaults), `dlq.payload` e
`frete_credenciais` (índice único). Não tem relação com o catálogo e não quebra o CI, que não
roda `alembic check`. Fica registrado para uma rodada própria — corrigir migration alheia às
pressas, no meio de outra mudança, é como se cria drift novo.

---

## Prefeituras: dados obtidos da comunidade (2026-11-26)

O usuário apontou as fontes centralizadas. Para NFS-e, a pepy MCP (downloads de pacotes
PyPI) ajudou a **achar** bibliotecas que embarcam dados — `nfselib-ginfes` e
`odoo-addon-l10n-br-nfse` — mas ambas só têm bindings SOAP e constantes, **sem URLs**. A
fonte que tinha o mapa completo é o `ACBrNFSeXServicos.ini` do ACBr, baixado para
`data/fontes/` (843 KB, Latin-1):

```
seções (município IBGE) : 5571
com provedor            : 4898
com URL https produção  : 1331
URLs http no arquivo    : 1629  (recusadas)
```

### O que foi aplicado

`python -m scripts.atualizar_municipios_acbr --aplicar` → **3648 municípios atualizados**.

| Medida | Antes | Depois |
|---|---|---|
| municípios com provedor definido | 0 | **3648** |
| com URL de produção https | 0 | **1195** |
| com URL de homologação https | 0 | **635** |
| `nacional_rest` (padrão nacional, sem URL própria) | 0 | **4375** |

**4375 municípios usam o padrão nacional** — para eles basta o endpoint único
(`sefin.nfse.gov.br`), não uma URL por prefeitura. É o caminho mais curto para cobertura real.

### O que foi recusado, e por quê

| Motivo | Municípios |
|---|---|
| provedor fora do enum | 691 |
| sem provedor no arquivo | 673 |
| sem URL https (só http ou vazia) | 559 |

**1.629 URLs do arquivo são `http://`.** Não entram: credencial e XML fiscal em texto claro
não vão para o banco mesmo que o provedor aceite.

### O enum de provedores estava incompleto

Tinha 6 provedores reais; o INI revelou 64. Adicionei os **22 com 10+ municípios** (fiorilli,
pronim, ipm, megasoft, futurize, el, elotech, sintese…), totalizando 36 valores. Ainda faltam
tributus (72), fisco (47), centi (45), elmar (40), abase (38), speedgov (36), tecnos (33),
aspec (28) — extensão de dado, não de capacidade.

**Adicionar provedor ao enum NÃO significa suportar emissão.** `criar_driver` continua
recusando quem não está em `MOTOR_ABRASF`, com motivo factual.

### Pendência

Nenhum município foi **homologado**: `homologados = 0`. Ter a URL certa não é ter a emissão
validada — falta a chamada real de status com certificado.
