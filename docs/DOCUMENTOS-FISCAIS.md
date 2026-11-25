# Documentos fiscais e representações impressas

Matriz do que o sistema deve cobrir, com etiqueta de confiança por linha. Este
documento é contrato: cada linha vira rota, tabela ou gerador de PDF.

Etiquetas: **[CONFIRMADO]** (verificado), **[INFERIDO]** (padrão observado),
**[A VALIDAR]** (depende de documentação oficial ou homologação).

## 1. Documentos fiscais

| Documento | Modelo | Uso | Chave | Autorizador | Etiqueta |
|---|---|---|---|---|---|
| NF-e | 55 | produtos, B2B, interestadual, importação | 44 dígitos | SEFAZ estadual | [CONFIRMADO] |
| NFC-e | 65 | venda ao consumidor final, PDV | 44 dígitos | SEFAZ estadual | [CONFIRMADO] |
| NFS-e | municipal / nacional | serviços | municipal varia; nacional usa **Id de DPS com 45 posições** | prefeitura ou SEFIN/ADN | [CONFIRMADO] |
| CT-e | 57 | transporte de cargas | 44 dígitos | SEFAZ estadual | [CONFIRMADO] |
| CT-e OS | 67 | transporte de pessoas/valores | 44 dígitos | SEFAZ estadual | [CONFIRMADO] |
| MDF-e | 58 | manifesto de documentos da carga | 44 dígitos | SEFAZ estadual | [CONFIRMADO] |
| ~~NFP-e~~ | — | — | — | — | **fora de escopo** (ver nota) |

Consequências de projeto já aplicadas:

- A biblioteca `notasbr` valida chave de **44 dígitos** (coluna Chave das linhas
  NF-e/NFC-e/CT-e/MDF-e). Ela **não** serve para NFS-e, que usa outro
  identificador — por isso NFS-e é módulo de tipo próprio.
- `fiscal_documents.chave` é `VARCHAR(60)`, não `CHAR(44)`: o tipo do documento é
  que define a validação. Um `CHECK` de 44 dígitos quebraria NFS-e.
- O enum `TipoDocumento` já cobre `nfse`, `nfe`, `nfce`, `cte`. `mdfe` e `nfpe`
  entram como migração de constraint quando a fase correspondente começar.

### Pré-requisitos de operação (não são código)

[CONFIRMADO] como pré-requisito de negócio, não como detalhe técnico:

- CNPJ ativo e credenciamento na SEFAZ estadual e/ou no município.
- Certificado digital A1 (arquivo) ou A3 (token) — o cofre da Fase 2 trata A1.
- Cadastros fiscais corretos: NCM, CEST, GTIN, CST/CSOSN e regras da Reforma
  Tributária.

Sem esses três, a emissão é rejeitada pelo autorizador, não pelo sistema. O
sistema deve **reportar a rejeição com o código e a mensagem do autorizador** —
nunca mascará-la como erro interno.

## 2. Representações impressas

Cada documento fiscal tem uma representação impressa distinta. Tratá-las como
"um PDF" é o erro que produz layout errado em produção.

| Representação | Base | Quando |
|---|---|---|
| DANFE A4 | NF-e (55) | padrão, operação normal |
| DANFE Simplificado | NF-e (55) | operação simplificada; também usado como etiqueta |
| DANFE NFC-e (cupom) | NFC-e (65) | venda no PDV |
| DANFSe | NFS-e | serviço |
| DACTE | CT-e | transporte |
| DAMDFE | MDF-e | manifesto |
| Etiqueta de envio | logística | separação e transporte da carga |

### 2.1 DANFE Simplificado — Etiqueta

Campos observados nas imagens anexadas pelo solicitante **[CONFIRMADO como
requisito]**, layout exato **[A VALIDAR]** contra o manual vigente:

| Bloco | Campos |
|---|---|
| Título | "DANFE SIMPLIFICADO - ETIQUETA" |
| Chave | código de barras (Code128) com a chave de 44 dígitos + o número em texto |
| Protocolo | número do protocolo de autorização de uso |
| Emitente | NOME/RAZÃO SOCIAL, CNPJ, UF, IE |
| Identificação | SÉRIE, Nº, EMISSÃO (data), OPERAÇÃO (0-ENTRADA / 1-SAÍDA) |
| Destinatário | NOME/RAZÃO SOCIAL, CNPJ/CPF, IE, ENDEREÇO, UF |
| Total | VALOR TOTAL DA NOTA FISCAL |

Decisões:

- O código de barras carrega a **chave de acesso** (44 dígitos), não o número da
  nota. É o que permite conferência por qualquer leitor e é o que a imagem mostra.
- A indicação 0/1 de operação vem de `ide/tpNF`, que a biblioteca `notasbr` já
  valida contra o CFOP (`TRIB-CFOP-002`).
- O XML autorizado prevalece sobre o PDF. O PDF é representação; em divergência,
  vale o XML.

### 2.2 Etiqueta de envio (por volume, estilo marketplace)

Campos observados nas imagens **[CONFIRMADO como requisito]**:

| Bloco | Campos |
|---|---|
| Cabeçalho | identificação do remetente/marketplace (logotipo e nome) |
| Resumo | `Volume: i/n`, `Peso (kg)`, `Nota fiscal: nº`, `Coleta: nº` |
| Código | código de barras + identificador legível (padrão observado `PREFIXO` + sequência + `V` + volume) |
| Destinatário | contato, telefone, endereço completo, CEP, complemento |
| Remetente | empresa, endereço, CEP |

Decisões:

- **Uma etiqueta por volume.** `Volume: 1/2` e `2/2` são páginas distintas, com o
  mesmo número de nota e códigos de barras distintos. Gerar uma etiqueta única
  para carga com 2 volumes é erro de operação logística.
- O identificador legível segue o padrão do emissor (`BLING0000018V1` no exemplo).
  Portanto é **configurável por tenant**, não constante de código.
- Peso é dado logístico, sem relação com valor fiscal. Vem do payload de
  expedição, não do XML da nota.
- A etiqueta não substitui o DANFE: são documentos diferentes, com finalidades
  diferentes. Um pode citar o número da nota; o outro é o documento fiscal.

## 3. O que ainda depende de validação humana

1. Layout exato do DANFE Simplificado e da etiqueta: as imagens mostram campos,
   não medidas, fontes nem normas de impressão. Confirmar contra o manual vigente.
2. ~~NFP-e~~: **removido do escopo em 2026-11-25** — ver nota ao fim desta seção.
3. MDF-e: confirmação de que entra no escopo imediato — é documento de transporte,
   com ciclo de vida próprio (abertura, encerramento, inclusão de NF-e).
4. Se a etiqueta de envio é responsabilidade do sistema ou do parceiro logístico.
   Hoje está modelada como representação do sistema.

## 4. Impacto no cronograma

O escopo original tinha 6 fases e cobria NFS-e, DANFSe e NF-e/DANFE. Os itens
acima adicionam:

- **Fase 7:** NF-e/NFC-e completas (emissão, eventos, DANFE A4, DANFE
  Simplificado/Etiqueta, cupom NFC-e).
- **Fase 8:** CT-e e MDF-e (DACTE, DAMDFE, ciclo de manifesto).
- **Fase 9:** etiqueta de envio por volume com integração logística (NFP-e removido).

Detalhe em [ROADMAP.md](ROADMAP.md).

## Nota sobre NFP-e — fora de escopo (decisão de 2026-11-25)

O NFP-e foi retirado do escopo por decisão do solicitante, com base em um fato
técnico: **não há padrão nacional publicado** de NFP-e que sirva de base para
implementação verificável. O que existe são iniciativas e modelos estaduais
heterogêneos, sem leiaute único, sem autorizador único e sem documentação pública
consolidada que este projeto possa seguir.

Implementar sem esse lastro significaria inventar leiaute, e inventar leiaute
fiscal é o pior resultado possível: produz documento com aparência de válido que
a SEFAZ estadual recusa — ou pior, aceita com dado errado.

**Se o cenário mudar**: havendo leiaute publicado (ou o layout específico de uma
UF que o cliente use), o caminho de entrada já existe — o catálogo de
representações é extensível e o `TipoDocumento` do banco já aceita o tipo. O que
falta é o documento de referência, não a arquitetura.
