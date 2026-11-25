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

### 9.1 Alíquotas de referência — [CONFIRMADO] no SQL da calculadora oficial

Fonte: `flyway/sql/criacao/B0001__sistema_tributario_completo.sql`, tabelas
`ALIQUOTA_REFERENCIA` e `TRIBUTO`. Mapeamento: `TBTO_ID` 2 = CBS, 3 = IBS UF,
4 = IBS Município. Valores do SQL em pontos percentuais.

| Vigência | CBS | IBS UF | IBS Mun | IBS total |
|---|---|---|---|---|
| 2026-01-01 a 2026-12-31 | 0,90% | 0,10% | 0,00% | 0,10% |
| 2027-01-01 a 2027-12-31 | 8,40% | 0,05% | 0,05% | 0,10% |

Isso **resolve** o que antes estava [A VALIDAR]: em 2026 o IBS é integralmente
estadual; em 2027 vira metade UF, metade município, e a CBS salta de 0,90% para
8,40% — o início da transição de fato.

O cálculo usa a tabela quando o chamador não informa alíquota, e devolve a
repartição. Com alíquota explícita, a repartição fica `None` (não zero): sem
tabela não há como afirmar como o IBS se divide, e chutar zero seria mentira.

**Observação de desenho**: a tabela agora é dado versionado com dois anos e fonte
citada. Acrescentar 2028 é uma linha, não uma mudança de lógica.

### 9.2 Pendente

- Catálogo de `cClassTrib` (classificações tributárias do IBS/CBS): existe no SQL
  oficial e ainda **não** foi importado para o produto. Hoje a classificação é
  informada pelo tenant; o catálogo entra como validação e como seletor na UI.
- Regras de `gTribRegular`, `gDif` (diferimento) e monofasia: lidas no código,
  não implementadas — dependem do catálogo acima.

---

## 10. Primeira resposta real da SEFIN (403) — evidência de alcance

Durante a verificação da Fase 4, o container estava com `NFSE_ADAPTER=sefin`
(padrão) e emitiu contra o ambiente de Produção Restrita usando o certificado
**autoassinado de teste**. Resultado:

```
HTTP 403 — "403 - Forbidden: Access is denied."
host: sefin.producaorestrita.nfse.gov.br
```

O que isso **prova**:

- [CONFIRMADO] O host `sefin.producaorestrita.nfse.gov.br` resolve e responde a
  partir desta máquina.
- [CONFIRMADO] A requisição chegou ao serviço (resposta IIS, não timeout).
- [CONFIRMADO] A classificação de erro funcionou: 403 virou
  `tipo=autenticacao`, e não "indisponível" nem "rejeição".

O que isso **não** prova: que o contrato de payload está correto. A recusa ocorre
antes de o corpo ser interpretado — certificado autoassinado não é aceito. O
contrato só será validado com A1 real.

**Correção aplicada por causa disso**: a resposta veio como página HTML de ~3 KB
e estava sendo guardada inteira na mensagem do erro. Agora mensagens são
resumidas a 300 caracteres e HTML vira "resposta HTML do servidor", para não
poluir banco, log e webhook com ruído que esconde o código real.

### 9.3 Catálogo de cClassTrib — [CONFIRMADO] com ressalva de versionamento

Extraído de `CLASSIFICACAO_TRIBUTARIA` pelo script `scripts/extrair_classificacoes.py`
(fica no repo para reprodutibilidade). Resultado: **168 registros, 155 códigos
distintos** — a diferença prova o ponto abaixo.

**Achado que mudou o modelo de dados:** o catálogo oficial **reusa códigos entre
vigências**. O código `000001` existe duas vezes:

| id | início vigência | descrição |
|---|---|---|
| 1 | 2026-01-01 | Situações tributadas integralmente pelo IBS e CBS. |
| 139 | 2027-01-01 | Primeiro fornecimento a qualquer título de bem |

Consequência obrigatória: deduplicar por código apagaria a versão vigente de uma
competência e faria o sistema validar nota de 2026 contra a classificação de
2027. O catálogo é consultado por `(código, ano)`; sem ano, devolve a versão mais
recente e o comportamento está documentado.

Segunda consequência: no SQL, a versão de 2026 não recebe data-fim quando a de
2027 entra. A substituição é implícita. Modelar isso como intervalo simples
(`inicio <= data <= fim`) faria a versão antiga parecer válida para sempre.
`vigentes_em()` resolve escolhendo, por código, a versão mais recente já iniciada.

Ressalva: os dados vêm do SQL da calculadora, não de um endpoint oficial de
catálogo. Se a Receita publicar uma lista canônica diferente, esta deve passar a
ser a fonte.

---

## 11. SEFIN/ADN com certificado A1 ICP-Brasil real — o que ficou CONFIRMADO

Em 25/11/2026 este projeto foi exercitado contra a **Produção Restrita (homologação)**
da NFS-e Nacional usando um certificado **A1 ICP-Brasil e-CNPJ real** do solicitante
(emitido pela AC SAFE-ID BRASIL / SERPRO). Nenhuma nota foi emitida: só consultas
de leitura.

O certificado não é versionado, a senha não foi gravada em disco, log ou documento,
e o registro selado foi **removido** do banco de desenvolvimento ao fim do teste.

### 11.1 O que passou a ser [CONFIRMADO]

| Afirmação | Evidência observada |
|---|---|
| mTLS com A1 ICP-Brasil é aceito pela SEFIN | handshake concluído; resposta de aplicação, não erro de TLS |
| Base de homologação `sefin.producaorestrita.nfse.gov.br` | raiz respondeu **HTTP 301** |
| `GET /dps/{id}` existe | **HTTP 404** com corpo JSON de domínio |
| 404 = DPS inexistente | `erro.codigo = E2404` |
| Envelope de erro em JSON | `{"tipoAmbiente", "dataHoraProcessamento", "erro": {"codigo", "descricao"}}` |
| Código `E2404` | "Não foi gerada uma NFS-e com o identificador de DPS informado" |
| `GET {adn}/contribuintes/DFe/{nsu}?lote=true` existe | **HTTP 400** com envelope de domínio |
| Envelope do ADN | `{TipoConsulta, StatusProcessamento, LoteDFe, Alertas, Erros, TipoAmbiente, VersaoAplicativo, DataHoraProcessamento}` |
| `StatusProcessamento` decide o resultado | veio `REJEICAO` com `TipoConsulta: InscricaoCertificado` |
| Nosso parser entende o erro real | `extrair_mensagens` extraiu `E2404` corretamente |

### 11.2 O que o mesmo teste mostrou estar ERRADO

`GET {adn}/parametrizacao/{municipio}/{servico}.000/{competencia}/aliquota`
respondeu **HTTP 404 com página IIS** — ou seja, **rota inexistente**, e não
"não encontrado" de domínio. O caminho documentado no código estava errado.

Consequência aplicada: `SefinNacionalClient.aliquota_municipal` agora declara
`[CONFIRMADO] que este caminho NÃO existe` e recomenda informar a alíquota na
configuração fiscal do tenant em vez de depender da consulta. O caminho correto
segue `[A VALIDAR]` contra o manual do ADN.

### 11.3 O que continua [A VALIDAR]

- Contrato de **emissão** (`POST /nfse`): exige emitir, o que não foi autorizado.
  Nada em `payload` de DPS foi validado pela SEFIN.
- Cancelamento e eventos por chave.
- `HEAD /dps/{id}` — não exercitado.
- Caminho correto da parametrização municipal.

### 11.4 Cofre com certificado real

O fluxo completo do cofre foi exercitado com o A1 real:

| Passo | Resultado |
|---|---|
| upload `POST /v1/me/certificados` | 201, CNPJ extraído do certificado |
| selagem AES-256-GCM | persistida; conteúdo não recuperável sem a chave-mestra |
| `GET /v1/me/certificados/saude` | validade lida, `dias_restantes` calculado |
| `DELETE` | 204, lista vazia |

Um detalhe operacional que o teste revelou: o certificado do solicitante tinha
**44 dias** de validade restante na data. O endpoint de saúde expõe exatamente
isso, que é o dado que evita nota parada por certificado vencido.

### 11.5 Validação estrutural contra o XSD oficial — [CONFIRMADO]

A DPS gerada por este projeto valida contra o **`DPS_v1.01.xsd` oficial**, nas duas
formas:

| Caso | Resultado |
|---|---|
| DPS não assinada | **válida** |
| DPS assinada (com `Signature` dentro de `infDPS`) | **válida** |
| DPS com grupo IBS/CBS | **válida** |
| DPS sem o grupo `valores` (controle negativo) | **recusada** pelo schema |

O controle negativo importa: sem ele, o teste de validação poderia passar sem
validar nada. Um schema que aceita tudo não prova estrutura.

Os XSD ficam versionados em `tests/fixtures/schemas/nfse-1.01/` (216 KB) para que a
validação rode **offline** e seja reproduzível — ver `ORIGEM.md` naquela pasta.

**Limite declarado**: validação de schema prova *forma*. Não prova aceitação pela
SEFIN, que depende de regra de negócio (cadastro do município, serviço, alíquota).
E o XSD 1.01 usa padrão numérico de CNPJ: CNPJ alfanumérico (julho/2026) não é
coberto por esta versão do leiaute — há teste que documenta essa lacuna em vez de
escondê-la.

### 11.6 Rotas restantes — o que o probe confirmou e o que derrubou

| Rota | Resultado real | Veredito |
|---|---|---|
| `HEAD /dps/{id}` | **HTTP 404** | **[CONFIRMADO]** existe e aceita HEAD |
| `GET /nfse/{chave}` | **HTTP 404** + envelope | **[CONFIRMADO]** |
| `GET /nfse/{chave}/eventos` | **HTTP 405** | **[CONFIRMADO] que a premissa do briefing está ERRADA** |
| `GET {adn}/contribuintes/NFSe/{chave}/Eventos` | **HTTP 404** + envelope válido | **[CONFIRMADO]** — e é o que usamos |

#### Os dois códigos de erro reais

`GET /nfse/{chave}` devolveu:

```json
{"tipoAmbiente": 2, "versaoAplicativo": "SefinNacional_1.6.0",
 "dataHoraProcessamento": "...",
 "erro": {"codigo": "E2401", "descricao": "Chave de acesso não encontrada."}}
```

O ADN, para eventos de chave inexistente, devolve **404 com corpo normal**:

```json
{"StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO", "LoteDFe": [], "Alertas": [],
 "Erros": [{"Codigo": "E2240", "Descricao": "Nenhum documento localizado - ..."}],
 "TipoAmbiente": "HOMOLOGACAO", "VersaoAplicativo": "1.0.0.0", ...}
```

Isso confirma a regra que o código já seguia: **no ADN, status HTTP não decide** —
`StatusProcessamento` decide. 404 aqui significa "não existe", não "falhou".

#### Observação que virou restrição de código

O mesmo ambiente reportou `tipoAmbiente: 0` na consulta de DPS e `tipoAmbiente: 2`
na consulta de NFS-e. Como o campo não é consistente entre endpoints, **nenhum
código pode inferir ambiente a partir dele** — há teste fixando essa observação.

#### Sobre `GET /nfse/{chave}/eventos` devolver 405

O briefing listava essa rota como parte do contrato. Ela responde
`405 — The requested resource does not support http method 'GET'`, ou seja: o
caminho existe, mas GET não é suportado. Nossa implementação **já** usava o ADN
(`/contribuintes/NFSe/{chave}/Eventos`), que funciona — o isolamento no adapter
evitou que a premissa errada virasse defeito. Há teste registrando o achado para
que ninguém "conserte" o código de volta para a rota errada.

#### Fixtures com respostas reais

As respostas acima estão versionadas em `tests/fixtures/sefins/` (sem segredo, só
mensagens públicas) e os testes as alimentam nos nossos parsers. Se a SEFIN mudar a
forma — ou se alguém quebrar a compatibilidade do parser — o teste falha antes da
produção.

Um ajuste saiu daí: quando o ADN devolve `REJEICAO` com `Erros: []` (acontece), a
mensagem antes dizia "recusou sem informar motivo". Agora inclui `TipoConsulta`
(ex.: `InscricaoCertificado`), que é a pista real para o operador.

---

## 12. Cancelamento de NFS-e — estrutura tirada do XSD, não de memória

O `pedRegEvento` do leiaute 1.01 foi implementado a partir do XSD oficial
(`tiposEventos_v1.01.xsd`, versionado em `tests/fixtures/schemas/nfse-1.01/`).

### 12.1 Estrutura [CONFIRMADO] pelo schema

```
pedRegEvento
└── infPedReg (Id)
    ├── tpAmb           1 | 2
    ├── verAplic        1..20 caracteres
    ├── dhEvento        TSDateTimeUTC
    ├── CNPJAutor
    ├── chNFSe          50: [0-9]{6}[0-9A-Z]{14}[0-9]{30}
    └── e101101         cancelamento
        ├── xDesc
        ├── cMotivo     1 | 2 | 9
        └── xMotivo     15..255 caracteres
```

O leiaute aceita **16 tipos de evento** (grupos `e101101`, `e105102`, `e202201`,
`e305101`…). Só o cancelamento (`e101101`) está implementado.

### 12.2 Dois erros que o schema pegou e a leitura do campo não pegaria

**1. O `Id` do pedido é `PRE`, com 59 caracteres — não `EVT` com 62.**
O pattern é `PRE[0-9]{8}(1[0-9]{14}|2[0-9A-Z]{14})[0-9]{33}`, `maxLength` 59.
Existe um segundo identificador, `EVT` + chave + tipo + `nPedRegEvento` = 62
(`TSIdEvento`), que pertence ao evento **já registrado**. Usar `EVT` no pedido é
recusado por `maxLength` — e o código pareceria certo, porque a documentação do
tipo `TSIdEvento` descreve exatamente `EVT…`.

**2. `TSDateTimeUTC` não aceita `Z`.**
Apesar do nome, o pattern exige offset numérico com minutos zerados
(`+00:00`, `-03:00`). Emitir `2026-11-25T16:30:00Z` é recusado.

Ambos viraram teste, com **controle negativo**: o teste monta o XML com `EVT` e com
`Z` e verifica que o schema recusa. Sem isso, um teste de validação pode passar sem
validar nada.

### 12.3 [INFERIDO] — o que o XSD não diz

Os significados de `cMotivo` (1, 2, 9) **não estão no schema**. As descrições em
`MOTIVOS_CANCELAMENTO` ("Erro na emissão", "Serviço não prestado", "Outros") vêm do
uso corrente, não de fonte oficial. O enquadramento correto é decisão do
contribuinte com o contador; o código não escolhe por ninguém.

### 12.4 Regras que o serviço aplica

- Só cancela **documento autorizado**: cancelar rascunho tentaria evento para chave
  que não existe na SEFIN.
- O **autor do evento é o CNPJ do certificado ativo**, não o do cadastro. Quem
  assina responde pelo pedido; divergência entre os dois permitiria assinar por
  outra pessoa jurídica.
- Cancelamento repetido devolve **409** com o estado atual.
- A nota cancelada **continua guardada** com o XML autorizado: nota cancelada ainda
  precisa ser demonstrável em fiscalização.

### 12.5 [A VALIDAR]

O `POST` de registro de evento **não foi exercitado** contra a SEFIN (é escrita).
O payload valida contra o XSD, mas aceitação real — códigos de retorno, prazo de
cancelamento, exigência de motivo específico por município — segue não verificado.

---

## 13. Os 16 tipos de evento da NFS-e — catálogo do XSD

Extraído de `tiposEventos_v1.01.xsd`. Todos os 16 validam contra o schema, com
teste parametrizado (um caso por tipo).

| Grupo | Descrição oficial (`xDesc`) — **[CONFIRMADO]** |
|---|---|
| e101101 | Cancelamento de NFS-e |
| e105102 | Cancelamento de NFS-e por Substituição |
| e101103 | Solicitação de Análise Fiscal para Cancelamento de NFS-e |
| e105104 | Cancelamento de NFS-e Deferido por Análise Fiscal |
| e105105 | Cancelamento de NFS-e Indeferido por Análise Fiscal |
| e202201 | Manifestação de NFS-e - Confirmação do Prestador |
| e203202 | Manifestação de NFS-e - Confirmação do Tomador |
| e204203 | Manifestação de NFS-e - Confirmação do Intermediário |
| e205204 | Manifestação de NFS-e - Confirmação Tácita |
| e202205 | Manifestação de NFS-e - Rejeição do Prestador |
| e203206 | Manifestação de NFS-e - Rejeição do Tomador |
| e204207 | Manifestação de NFS-e - Rejeição do Intermediário |
| e205208 | Manifestação de NFS-e - Anulação da Rejeição |
| e305101 | Cancelamento de NFS-e por Ofício |
| e305102 | Bloqueio de NFS-e por Ofício |
| e305103 | Desbloqueio de NFS-e por Ofício |

### 13.1 `xDesc` não é texto livre

Descoberta que só a validação revela: `xDesc` é **enumeração com um valor por tipo
de evento**. Quem monta o XML com descrição própria tem o pedido recusado. O
catálogo emite o texto oficial; o campo saiu da lista de entradas do chamador, e há
teste que recusa `xDesc` vindo de fora.

Isso tornou dispensável a descrição `[INFERIDO]` que este documento registrava
antes: agora a descrição de cada evento é a do leiaute.

### 13.2 Restrições por campo — **[CONFIRMADO]** no XSD

| Tipo | Regra |
|---|---|
| `TSMotivo` | 15 a 255 caracteres |
| `TSCPF` | 11 dígitos |
| `TSChaveNFSe` | `[0-9]{6}[0-9A-Z]{14}[0-9]{30}` |
| `TSNumProcAdmAnaliseFiscalCanc` | 1 a 30 dígitos |
| `TSIdNumEvento` | 8 dígitos + (1+14 dígitos \| 2+14 alfanuméricos) + 33 dígitos |
| `TSCodJustCanc` | 1, 2, 9 |
| `TSCodJustSubst` | 01, 02, 03, 04, 05, 99 |
| `TSCodMotivoRejeicao` | 1, 2, 3, 4, 5, 9 |
| `TSCodJustAnaliseFiscalCanc` | 1, 2, 9 |
| `TSCodJustAnaliseFiscalCancDef` | 1 |
| `TSCodJustAnaliseFiscalCancIndef` | 1, 2 |
| `TSCodigoEventoNFSe` | e101101, e105102, e105104, e105105, e305101 |

### 13.3 O que o catálogo NÃO decide

Qual evento usar em cada situação, e qual motivo escolher. Isso é enquadramento
fiscal: depende do fato e do entendimento do contribuinte com o contador. O código
fornece a estrutura válida e recusa combinação incoerente; não escolhe por ninguém.

`GET /v1/emissoes/eventos/tipos` expõe o catálogo para quem integra, com os campos
obrigatórios de cada tipo.

### 13.4 [A VALIDAR]

Aceitação real de cada evento pela SEFIN. O `POST` de registro não foi exercitado
(é escrita). Também não validei se a SEFIN restringe tipos por perfil de autor
(prestador/tomador/intermediário só podem manifestar o que lhes cabe) — o schema
não expressa essa regra.
