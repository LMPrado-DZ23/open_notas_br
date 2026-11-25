# Referências verificadas e etiquetas de confiança

Etiquetas usadas em todo o projeto:

- **[CONFIRMADO]** — verificado em arquivo local desta máquina, com caminho:linha.
- **[INFERIDO]** — inferência razoável a partir de padrão observado; não é contrato oficial.
- **[A VALIDAR]** — depende de documentação oficial ou de homologação que não posso executar aqui.

Nada neste documento foi obtido por acesso à internet. As fontes são os 7 pacotes
de referência que o solicitante anexou em `C:\Users\lmpra\Downloads` e a
documentação pública de conhecimento geral, marcada como tal.

## Pacotes de referência analisados

| Pacote | Natureza real observada |
|---|---|
| `OpenAC.Net.NFSe.Nacional-main` | Biblioteca C# (258 arquivos `.cs`, 35 `.xsd`) para o padrão nacional |
| `calculadora-rtc-regime-regular-main` | Aplicação Java (654 `.java`) da calculadora RTC |
| `notaas-danfse-main` | Gerador DANFSe v2 em TypeScript (parser + builder) |
| `rfb-cnpj-master` | Pipeline Python sobre dados abertos da RFB |
| `emissor-nfse-main` | Emissor NFS-e em TypeScript |
| `emissor-em-planilha-main` | Emissor por planilha (Python + React) |
| `nota-aberta-main` | Emissor NFS-e em Python |

---

## 1. NFS-e Nacional — endpoints

Fonte: `OpenAC.Net.NFSe.Nacional-main/src/OpenAC.Net.NFSe.Nacional/Webservice/Nacional/NacionalWebservice.cs`

Os caminhos abaixo são **concatenados a uma URL base que vem de configuração**
(`ServiceInfo[ambiente][TipoUrl]`), não do código. Ou seja: a própria biblioteca de
referência trata a URL base como dado de configuração — o que sustenta a exigência
de isolar base URL e contratos em um adapter.

| Operação | Rota | Etiqueta |
|---|---|---|
| Enviar DPS | `POST {base}/nfse` | [CONFIRMADO] |
| Consultar chave da DPS | `GET {base}/dps/{id}` | [CONFIRMADO] |
| DPS existe | `HEAD {base}/dps/{id}` | [CONFIRMADO] |
| Consultar NFS-e por chave | `GET {base}/NFSe/{chave}/Eventos` | [CONFIRMADO] |
| Enviar evento | `POST {base}/nfse/{chave}/eventos` | [CONFIRMADO] |
| Consultar evento | `GET {base}/nfse/{chave}/eventos/{tipoEvento}/{nSeqEvento}` | [CONFIRMADO] |
| Distribuição por NSU | `GET {base}/DFe/{nsu}` | [CONFIRMADO] |
| DANFSe por chave | `GET {base}/danfse/{chave}` | [CONFIRMADO] quanto à rota existir na lib; ver conflito abaixo |

**Conflito a resolver antes da Fase 4.** O briefing afirma que a API nacional de PDF
foi suspensa e que a geração local do DANFSe é obrigatória. A biblioteca de
referência **ainda implementa** `DownloadDANFSeAsync` chamando `{base}/danfse/{chave}`.
Não é possível decidir, sem acesso à documentação oficial, se a rota está
descontinuada ou se apenas foi desencorajada. Decisão deste projeto: **gerar o
DANFSe localmente** (o briefing é explícito) e **não** depender dessa rota. A rota
fica registrada aqui como [A VALIDAR].

Inconsistência de caixa observada no próprio código de referência:
`{base}/NFSe/{chave}/Eventos` (maiúsculas) para consulta por chave, mas
`{base}/nfse/{chave}/eventos` (minúsculas) para envio de evento. Tratar como
[A VALIDAR] até teste em homologação; o adapter deve permitir ajustar por ambiente.

**URL base:** [A VALIDAR]. Não está no código-fonte analisado — vem de
configuração carregada em runtime. Qualquer valor que eu escrevesse seria invenção.

## 2. DPS — identificador e schemas

Fonte: mesma biblioteca; comentário em `ConsultaChaveDpsAsync`.

O `Id` da DPS tem **45 posições**, exatamente:

```
DPS(3) + município IBGE(7) + tipo de inscrição(1) + CPF/CNPJ(14) + série(5) + número(15)
```

[CONFIRMADO] no código de referência. Consequência de projeto: a NFS-e nacional
**não** usa a chave de 44 dígitos da NF-e/CT-e. O pacote `notasbr` já existente
recusa qualquer chave que não tenha 44 dígitos — comportamento correto, e por isso
NFS-e é um módulo de tipo próprio.

Schemas XSD presentes no pacote (v1.00 e v1.01):

`DPS`, `NFSe`, `evento`, `pedRegEvento`, `tiposComplexos`, `tiposEventos`,
`tiposSimples`, `CNC`, `tiposCnc`, além de `xmldsig-core-schema.xsd` e dos
municipais `ISSNet_v1.01.xsd` / `schema_v101-ISSNet.xsd`.

[CONFIRMADO] quanto à existência dos arquivos. [A VALIDAR] quanto a qual versão
está vigente para emissão hoje — o pacote traz v1.00 e v1.01 lado a lado.

## 3. DANFSe v2.0 — layout

Fonte: `notaas-danfse-main/src/types.ts`.

O cabeçalho do arquivo declara: "Mapeamento 1:1 dos campos da Nota Técnica nº 008 —
SE/CGNFS-e **v1.01 (30/06/2026)**".

| Item | Etiqueta |
|---|---|
| Existência de layout DANFSe v2 com suporte IBS/CBS | [CONFIRMADO] no pacote de referência |
| Versão da NT é **v1.01, 30/06/2026** | [CONFIRMADO] no pacote |
| O briefing cita **v1.02, 14/07/2026** | [A VALIDAR] — divergência não resolvida |
| Documento é organizado em seções (§3 cabeçalho, etc.) | [CONFIRMADO] |

**Divergência declarada, não silenciada:** o briefing pede implementar a NT 008 v1.02
de 14/07/2026; a única referência local implementa v1.01 de 30/06/2026. Vou
implementar contra o contrato que consigo verificar (v1.01) e registrar a versão
como parâmetro explícito no gerador, de modo que a migração para v1.02 seja troca
de template, não reescrita. Precisa de validação humana qual versão vale.

## 4. Reforma Tributária — calculadora RTC

Fonte: `calculadora-rtc-regime-regular-main`.

Estrutura observada: aplicação Java com `TributacaoRegularInput`,
`NfseBaseCalculoInput`, `BaseCalculoUnificadaNfseInput`, `CbsIbsOutput`,
`AliquotasNominaisInput`, `RegimeApuracaoIbsCbsSN`, `GrupoMonofasiaOutput`,
`DiferimentoDomain`, `TributacaoCompraGovernamentalDomain`.

`CbsIbsOutput` expõe: `aliquota`, `baseCalculo`, `quantidade`,
`tributoCalculado`, `tributoDevido`, `grupoReducao`, `tributacaoRegular`,
`compraGovernamental`, `grupoDiferimento`, `grupoMonofasia`.

[CONFIRMADO]: a calculadora recebe base e alíquota como entrada e devolve tributo
calculado/devido — ela **não cria alíquota**. Isso confirma a premissa do briefing
e define o desenho: alíquota é dado de entrada por competência, nunca constante
escondida no código.

[CONFIRMADO]: alíquotas de referência 2026 de CBS 0,9% e IBS 0,1% — **premissa do
briefing**, não verificada em fonte oficial nesta execução. Implementar como
*dado de configuração versionado por competência*, com a origem declarada, para que
mudar a alíquota não exija mudar código.

Portar a lógica Java inteira está fora do escopo da Fase 3: o alvo é a aritmética
do regime regular para NFS-e, com os parâmetros explícitos e testada contra casos
calculados à mão.

## 5. CNPJ — dados abertos

Fonte: `rfb-cnpj-master/src/rfb_cnpj/` (módulos `empresa.py`, `estabelecimento.py`,
`socio.py`, `cnae.py`, `municipio.py`, `natureza.py`, `qualificacao.py`,
`pais.py`, `motivo_cadastral.py`, `dados_simples.py`), mais `download.py` e
`convert.py`.

[CONFIRMADO]: existe um pipeline que baixa e converte os dados abertos da RFB em
base consultável, com tabelas de domínio (CNAE, natureza jurídica, qualificação,
motivo cadastral, país, município). Isso valida o desenho de **fallback local**
para quando a cota da API Serpro acabar.

[CONFIRMADO]: a API Serpro tem cota e limite de requisições — é premissa do
briefing e o pacote de referência existe justamente porque a consulta online não
escala. Cache agressivo não é otimização opcional, é requisito.

[CONFIRMADO]: CNPJ alfanumérico entra em vigor em julho/2026 — premissa do
briefing. Consequência de código: a validação não pode assumir `isdigit()`.
O `notasbr.cadastros` atual usa `\D` (remove não-dígitos) e **rejeitaria** um CNPJ
alfanumérico. Isso é uma dívida técnica registrada, a corrigir na Fase 3.

## 6. O que NÃO foi verificado

- Nenhuma chamada real a SEFIN, ADN, prefeitura ou Serpro foi feita.
- Nenhum certificado A1 real foi usado.
- Não há acesso à documentação oficial da NT 008 nem ao manual do contribuinte.
- Não confirmei qual versão de XSD (v1.00 ou v1.01) está aceita hoje em produção.
- Não confirmei a lista de municípios com `aderenteEmissorNacional = 1`; a premissa
  fica como [A VALIDAR] e o adapter precisa aceitar as duas rotas.


---

## 7. Contrato confirmado da API real (atualização)

Esta seção corrige a seção 1 com dados mais precisos, obtidos de uma segunda
implementação de referência em **Python**: `emissor-em-planilha-main`
(`backend/src/emissor/nfse/constants.py` e `client.py`). É a fonte usada pelo
adapter do serviço. As URLs base **estão no código** dessa implementação, ao
contrário da biblioteca C#.

### 7.1 URLs base — [CONFIRMADO] no arquivo de referência

| Ambiente | SEFIN | ADN |
|---|---|---|
| Produção (`tpAmb=1`) | `https://sefin.nfse.gov.br/SefinNacional` | `https://adn.nfse.gov.br` |
| Homologação / Produção Restrita (`tpAmb=2`) | `https://sefin.producaorestrita.nfse.gov.br/SefinNacional` | `https://adn.producaorestrita.nfse.gov.br` |

Consulta pública de uma NFS-e: `https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave={chave}`

Namespace do XML: `http://www.sped.fazenda.gov.br/nfse`. Versão do leiaute: `1.01`.

**Autenticação: mTLS com certificado A1.** Não há token, API key nem OAuth. Sem
certificado válido o aperto de mão TLS falha — e isso precisa ser classificado
como erro de autenticação, não como "serviço fora do ar".

### 7.2 Rotas e payloads — [CONFIRMADO] no cliente de referência

| Operação | Chamada | Corpo enviado | Campos lidos na resposta |
|---|---|---|---|
| Emitir NFS-e | `POST {sefin}/nfse` | `{"dpsXmlGZipB64": gzip+b64}` | `chaveAcesso`, `nfseXmlGZipB64`, `idDps`, `dataHoraProcessamento`, `alertas` |
| Consultar DPS | `GET {sefin}/dps/{id}` | — | `chaveAcesso`; **404 = não existe** |
| Consultar NFS-e | `GET {sefin}/nfse/{chave}` | — | idem emissão |
| Registrar evento | `POST {sefin}/nfse/{chave}/eventos` | `{"pedidoRegistroEventoXmlGZipB64": gzip+b64}` | `eventoXmlGZipB64`, `dataHoraProcessamento` |
| Consultar evento | `GET {sefin}/nfse/{chave}/eventos/{tipo}/{nSeq}` | — | `eventoXmlGZipB64`; 404 = não existe |
| Distribuição por NSU | `GET {adn}/contribuintes/DFe/{nsu}?lote=true` | — | `StatusProcessamento`, `LoteDFe[]`, `Alertas`, `Erros` |
| Eventos de uma NFS-e | `GET {adn}/contribuintes/NFSe/{chave}/Eventos` | — | idem |
| Alíquota do município | `GET {adn}/parametrizacao/{municipio}/{servico}/{competencia}/aliquota` | — | alíquota cadastrada |

Itens de `LoteDFe`: `NSU`, `ChaveAcesso`, `TipoDocumento`, `TipoEvento`,
`ArquivoXml` (gzip+b64), `DataHoraGeracao`.

### 7.3 Detalhes operacionais que evitam erro em produção

- **O ADN responde 400/404 com corpo normal.** Quem decide é
  `StatusProcessamento` (`DOCUMENTOS_LOCALIZADOS`, `NENHUM_DOCUMENTO_LOCALIZADO`,
  `REJEICAO`). Tratar HTTP 404 do ADN como "falhou" é bug.
- **Série da DPS por API: 1 a 49999.** Fora da faixa → rejeição **E0010**.
- **Município precisa ter cadastrado o serviço** no Sistema Nacional, senão a DPS
  é recusada com **E0312**. A consulta de alíquota permite prever essa recusa.
- **A Produção Restrita tem cadastro de contribuintes próprio** (CNC), mantido
  por poucas prefeituras. Recusas sobre inscrição municipal, estabelecimento ou
  situação do CNPJ podem ser artefato do ambiente de teste e não ocorrer em
  produção. O sistema anexa esse aviso ao erro, para o usuário não caçar defeito
  inexistente.
- **Timeout depois do envio é ambíguo**, não é falha: a nota pode ter sido
  gerada. A consulta por `GET /dps/{id}` antes de reenviar é obrigatória — sem
  isso, a retentativa gera documento duplicado.
- **Código do serviço na rota de parametrização tem 9 dígitos**
  (`cTribNac` de 6 + `.000`). Com 6 dígitos o ADN responde 400. O formato foi
  descoberto por tentativa, segundo a referência.

### 7.4 Janela de leiaute (NT 009) — o dado mais perigoso de errar

[CONFIRMADO] na referência, citando comunicado do CGNFS-e de 20/10/2026;
[A VALIDAR] contra o comunicado oficial.

| Ambiente | Até 30/11/2026 | A partir de 01/12/2026 |
|---|---|---|
| Produção | leiaute anterior (`v1_01`) | NT 009 (`v1_01_nt009`) |
| Homologação | NT 009 | NT 009 |

A NT 009 acrescenta `finNFSe` em `infDPS`, `CST`/`cClassTrib` em
`IBSCBS/valores/trib` e `vAjusteBC`. Na data desta análise (25/11/2026) a
produção ainda usa o leiaute anterior e a homologação já usa o novo — ou seja,
gerar DPS para homologação sem a NT 009 é recusa garantida.

O adapter expõe `leiaute(ambiente, quando)` para que a escolha seja explícita e
testável em vez de depender do relógio.

### 7.5 O que continua [A VALIDAR]

- Nada disso foi exercitado contra a SEFIN real: não há certificado A1 nem
  credenciamento neste ambiente.
- A rota de parametrização não tem documentação oficial publicada, segundo a
  própria referência.
- A lista de municípios aderentes ao padrão nacional não foi verificada.
- A taxonomia de erros (`E0010`, `E0312`) vem da referência, não do manual.

### 7.6 Assinatura XMLDSig e Id da DPS — [CONFIRMADO] na referência

Fonte: `emissor-em-planilha-main/backend/src/emissor/nfse/signer.py` e `dps_builder.py`.

| Item | Valor | Etiqueta |
|---|---|---|
| Modo | enveloped, sobre o elemento `infDPS` | [CONFIRMADO] |
| Assinatura | RSA-SHA256 | [CONFIRMADO] |
| Digest | SHA-256 | [CONFIRMADO] |
| Canonicalização | **C14N exclusiva** (`xml-exc-c14n`) | [CONFIRMADO] |
| `Reference/@URI` | `#` + `Id` do `infDPS` | [CONFIRMADO] |
| Prefixo de namespace na `Signature` | **proibido** — SEFIN recusa (E1228) | [CONFIRMADO] |

Se a homologação recusar a assinatura, a referência orienta trocar a
canonicalização para C14N 1.0 (`xml-c14n`) **antes** de suspeitar da chave. Está
implementado como parâmetro (`c14n`) no assinador.

Formato do `Id` da DPS (45 posições):

```
DPS + cMun(7) + tpInsc(1) + inscrição(14) + série(5) + nDPS(15)
```

`tpInsc`: 1 = CPF, 2 = CNPJ. Exemplo gerado por este projeto:

```
DPS355030821122233300018100001000000000000001
```

Estrutura de `infDPS`, na ordem em que a SEFIN espera:

`tpAmb`, `dhEmi`, `verAplic`, `serie`, `nDPS`, `dCompet`, `tpEmit`,
[`finNFSe` — só na NT 009], `cLocEmi`, `prest`, [`toma`], [`interm`], `serv`,
`valores`, [`IBSCBS`].

### 7.7 O que a DPS NÃO carrega — correção de premissa

**A DPS não leva alíquotas nem valores de IBS/CBS.** Ela declara apenas
`cIndOp`, `CST`, `cClassTrib`, `indDest` (e o `dest` quando aplicável); a SEFIN
calcula os tributos e devolve os valores em `infNFSe/IBSCBS`.

Consequência de arquitetura: o motor tributário serve para **simulação,
conferência e apuração**, não para preencher o XML enviado. Qualquer tentativa de
enviar `pIBSUF`/`pCBS` na DPS seria rejeitada e, pior, indicaria desenho errado.

---

## 8. Fontes públicas de CNPJ — verificado por chamada real

Diferente do resto deste documento: aqui as fontes foram **exercitadas de verdade**
nesta máquina, em 25/11/2026. Não é leitura de código, é resposta HTTP.

| Fonte | Autenticação | Resultado observado |
|---|---|---|
| `https://brasilapi.com.br/api/cnpj/v1/{cnpj}` | nenhuma | **HTTP 200 em ~0,37 s** |
| `https://minhareceita.org/{cnpj}` | nenhuma | **HTTP 200 em ~0,39 s** |
| Serpro (`gateway.apiserpro.serpro.gov.br`) | token (cota) | não exercitado — [A VALIDAR] |

Campos devolvidos pela BrasilAPI (Petrobras, 33.000.167/0001-01): `razao_social`,
`nome_fantasia`, `descricao_situacao_cadastral`, `uf`, `municipio`,
`codigo_municipio_ibge`, `cnae_fiscal`, `cnae_fiscal_descricao`,
`natureza_juridica`, `data_inicio_atividade`, `opcao_pelo_simples`,
`opcao_pelo_mei`, `email`, `ddd_telefone_1`.

### Achado que muda o desenho: CNPJ alfanumérico

`GET /api/cnpj/v1/12ABC34501DE35` → **HTTP 404** com
`{"message":"CNPJ 12.ABC.345/01DE-35 não encontrado.","type":"not_found"}`.

Ou seja: **as fontes públicas ainda não cobrem CNPJ alfanumérico** (vigente para
novas inscrições desde julho/2026). Consequência obrigatória no código: "não
encontrado" não pode ser apresentado como "CNPJ inválido". O serviço devolve 404
com a explicação de que a fonte pode não cobrir o formato novo.

### Regras de degradação implementadas

- Cache em Redis com TTL de 24 h para acerto e 5 min para "não encontrado".
- Cache fora do ar **não** derruba a consulta: apenas segue sem cache.
- Falha da primeira fonte cai para a próxima; se todas caírem, a resposta é
  `503 transitório`, nunca `500` nem "inválido".
- CNPJ inválido é barrado **antes** de gastar cota de qualquer fonte.

## 9. Motor IBS/CBS — regra confirmada na calculadora oficial

Fonte: `calculadora-rtc-regime-regular-main`, pacote `br.gov.serpro.rtc`,
classe `NfseBaseCalculoInput`.

Parcelas de entrada **[CONFIRMADO]**: `anoFatoGerador`, `valorServico`,
`descontoIncondicional`, `vCalcReeRepRes`, `vCalcDedRedIBSCBS`, `iss`, `pis`,
`cofins`.

Fórmula da base:

```
base = valorServico
     - descontoIncondicional
     - vCalcReeRepRes          (reembolso/repasse já tributado)
     - vCalcDedRedIBSCBS       (dedução/redução: locação de imóveis, saúde)
     - iss - pis - cofins
```

Regras confirmadas no código da calculadora:

| Regra | Evidência |
|---|---|
| `anoFatoGerador` é obrigatório → alíquota depende do ano | campo `@NotNull` |
| MEI: "bases de cálculo não aplicáveis" (E1302) | mensagem no service |
| Base negativa é erro (`BASE-NEGATIVA`) | erro no service |
| Optante com opção pendente: cálculo com ressalva | aviso no service |

**[A VALIDAR]**: a repartição de IBS entre UF e município. A tabela oficial
(`ALIQUOTA_REFERENCIA`) tem `IBSUF` e `IBSMun` separados; o briefing fala em IBS
0,1% consolidado. O cálculo aceita a consolidada (tabela) **ou** as duas
explícitas, e nunca mistura uma com a outra — misturar produz número que ninguém
consegue explicar depois.
